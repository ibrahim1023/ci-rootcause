from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Any, Callable

from src.agents.diff_analysis import run_diff_analysis
from src.agents.failure_classification import run_failure_classification
from src.agents.fix_planner import run_fix_planner
from src.agents.log_ingest import run_log_ingest
from src.agents.pr_creation import run_pr_creation
from src.agents.reporter import run_reporter
from src.agents.root_cause_ranker import run_root_cause_ranker


class OrchestrationError(RuntimeError):
    """Raised when deterministic orchestration cannot be completed."""


AgentHandler = Callable[["PipelineState"], dict[str, Any]]


@dataclass(frozen=True)
class AgentRegistration:
    name: str
    depends_on: tuple[str, ...]
    handler: AgentHandler


@dataclass
class DeterministicAgentRegistry:
    _registrations: dict[str, AgentRegistration] = field(default_factory=dict)
    _registration_order: list[str] = field(default_factory=list)

    def register(self, registration: AgentRegistration) -> None:
        if registration.name in self._registrations:
            raise OrchestrationError(f"Duplicate agent registration: {registration.name}")

        for dependency in registration.depends_on:
            if dependency == registration.name:
                raise OrchestrationError(f"Agent cannot depend on itself: {registration.name}")

        self._registrations[registration.name] = registration
        self._registration_order.append(registration.name)

    def get(self, name: str) -> AgentRegistration:
        try:
            return self._registrations[name]
        except KeyError as exc:
            raise OrchestrationError(f"Unknown agent registration: {name}") from exc

    def resolve_order(self) -> list[str]:
        pending = {
            name: set(registration.depends_on)
            for name, registration in self._registrations.items()
        }

        resolved: list[str] = []
        while pending:
            ready = [name for name, deps in pending.items() if not deps]
            if not ready:
                unresolved = sorted(pending)
                raise OrchestrationError(f"Cyclic or missing dependencies detected: {unresolved}")

            ready.sort(key=self._registration_order.index)
            current = ready[0]
            resolved.append(current)
            del pending[current]
            for deps in pending.values():
                deps.discard(current)

        return resolved


@dataclass(frozen=True)
class ADKRuntimeScaffold:
    """ADK-facing runtime scaffold with deterministic agent registration."""

    registry: DeterministicAgentRegistry

    @property
    def backend(self) -> str:
        return "google-adk" if find_spec("google.adk") else "google-adk-scaffold"

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "depends_on": list(self.registry.get(name).depends_on),
            }
            for name in self.registry.resolve_order()
        ]


@dataclass(frozen=True)
class RepoContext:
    repository: str
    target_branch: str = "main"


@dataclass(frozen=True)
class CommitContext:
    commit: str
    base_commit: str
    head_commit: str


@dataclass(frozen=True)
class RunContext:
    run_id: str
    timestamp: str
    job_id: str | None = None


@dataclass(frozen=True)
class PipelineConfig:
    ci_provider: str
    provider_adapter: str
    repo: RepoContext
    commit: CommitContext
    run: RunContext


@dataclass(frozen=True)
class PipelineRequest:
    raw_log: str
    raw_diff: str
    timestamp: str
    commit: str
    run_id: str
    base_commit: str
    head_commit: str
    output_dir: str
    create_fix_pr: bool = False
    dry_run: bool = False
    github_token: str | None = None
    repository: str | None = None
    target_branch: str | None = None
    validated_changes: list[dict[str, str]] = field(default_factory=list)
    fail_fast: bool = False
    config: PipelineConfig | None = None
    use_adk_runtime: bool | None = None


@dataclass
class PipelineState:
    request: PipelineRequest
    shared: dict[str, Any] = field(default_factory=dict)
    agent_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    agent_status: dict[str, str] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)
    pipeline_status: str = "pending"
    config: PipelineConfig | None = None


def _run_log_ingest_agent(state: PipelineState) -> dict[str, Any]:
    return run_log_ingest(raw_log=state.request.raw_log, timestamp=state.config.run.timestamp)


def _run_diff_analysis_agent(state: PipelineState) -> dict[str, Any]:
    return run_diff_analysis(raw_diff=state.request.raw_diff)


def _run_failure_classification_agent(state: PipelineState) -> dict[str, Any]:
    log_output = state.agent_outputs["log_ingest"]
    diff_output = state.agent_outputs["diff_analysis"]
    return run_failure_classification(
        failure_events=log_output["failure_events"],
        dependency_change_flags=diff_output["dependency_change_flags"],
    )


def _run_root_cause_ranker_agent(state: PipelineState) -> dict[str, Any]:
    log_output = state.agent_outputs["log_ingest"]
    diff_output = state.agent_outputs["diff_analysis"]
    classification_output = state.agent_outputs["failure_classification"]
    return run_root_cause_ranker(
        failure_graph=log_output["failure_graph"],
        changed_files=diff_output["changed_files"],
        changed_modules=diff_output["changed_modules"],
        dependency_change_flags=diff_output["dependency_change_flags"],
        classification=classification_output["classification"],
    )


def _run_fix_planner_agent(state: PipelineState) -> dict[str, Any]:
    ranker_output = state.agent_outputs["root_cause_ranker"]
    classification_output = state.agent_outputs["failure_classification"]
    primary = ranker_output["primary_root_cause"]
    if not primary:
        raise OrchestrationError("Fix planner requires a primary_root_cause from ranker output")
    return run_fix_planner(
        {
            "classification": classification_output["classification"],
            "primary_root_cause": primary,
        }
    )


def _build_reporter_payload(state: PipelineState) -> dict[str, Any]:
    ranker_output = state.agent_outputs["root_cause_ranker"]
    classification_output = state.agent_outputs["failure_classification"]
    fix_output = state.agent_outputs["fix_planner"]

    primary = ranker_output["primary_root_cause"]
    if not primary:
        raise OrchestrationError("Reporter requires a primary_root_cause from ranker output")

    return {
        "summary": f"{classification_output['classification']} failure: {primary['title']}",
        "classification": classification_output["classification"],
        "confidence": ranker_output["confidence"],
        "primary_root_cause": primary,
        "ranked_causes": ranker_output["ranked_causes"],
        "fix_steps": fix_output["fix_steps"],
        "meta": {
            "commit": state.config.commit.commit,
            "run_id": state.config.run.run_id,
        },
    }


def _run_reporter_agent(state: PipelineState) -> dict[str, Any]:
    payload = _build_reporter_payload(state)
    return run_reporter(payload=payload, output_dir=state.request.output_dir)


def _run_pr_creation_agent(state: PipelineState) -> dict[str, Any]:
    ranker_output = state.agent_outputs["root_cause_ranker"]
    classification_output = state.agent_outputs["failure_classification"]
    fix_output = state.agent_outputs["fix_planner"]
    primary = ranker_output["primary_root_cause"]

    allowed_files = sorted({step["file"] for step in fix_output["fix_steps"] if step.get("file")})
    payload = {
        "create_fix_pr": state.request.create_fix_pr,
        "dry_run": state.request.dry_run,
        "github_token": state.request.github_token or "",
        "repository": state.config.repo.repository,
        "target_branch": state.config.repo.target_branch,
        "summary": f"{classification_output['classification']} failure: {primary['title']}",
        "classification": classification_output["classification"],
        "confidence": ranker_output["confidence"],
        "primary_root_cause": primary,
        "meta": {
            "run_id": state.config.run.run_id,
            "base_commit": state.config.commit.base_commit,
            "head_commit": state.config.commit.head_commit,
        },
        "allowed_files": allowed_files,
        "validated_changes": state.request.validated_changes,
    }
    return run_pr_creation(payload=payload)


def build_default_registry() -> DeterministicAgentRegistry:
    registry = DeterministicAgentRegistry()
    registry.register(
        AgentRegistration(
            name="log_ingest",
            depends_on=(),
            handler=_run_log_ingest_agent,
        )
    )
    registry.register(
        AgentRegistration(
            name="diff_analysis",
            depends_on=(),
            handler=_run_diff_analysis_agent,
        )
    )
    registry.register(
        AgentRegistration(
            name="failure_classification",
            depends_on=("log_ingest", "diff_analysis"),
            handler=_run_failure_classification_agent,
        )
    )
    registry.register(
        AgentRegistration(
            name="root_cause_ranker",
            depends_on=("log_ingest", "diff_analysis", "failure_classification"),
            handler=_run_root_cause_ranker_agent,
        )
    )
    registry.register(
        AgentRegistration(
            name="fix_planner",
            depends_on=("root_cause_ranker", "failure_classification"),
            handler=_run_fix_planner_agent,
        )
    )
    registry.register(
        AgentRegistration(
            name="reporter",
            depends_on=("root_cause_ranker", "failure_classification", "fix_planner"),
            handler=_run_reporter_agent,
        )
    )
    registry.register(
        AgentRegistration(
            name="pr_creation",
            depends_on=("root_cause_ranker", "failure_classification", "fix_planner"),
            handler=_run_pr_creation_agent,
        )
    )
    return registry


def _blocked_dependencies(
    registration: AgentRegistration,
    state: PipelineState,
) -> list[str]:
    blocked: list[str] = []
    for name in registration.depends_on:
        if state.agent_status.get(name) in {"failed", "skipped"}:
            blocked.append(name)
    return blocked


def resolve_pipeline_config(request: PipelineRequest) -> PipelineConfig:
    if request.config is not None:
        return request.config

    return PipelineConfig(
        ci_provider="github-actions",
        provider_adapter="github",
        repo=RepoContext(
            repository=request.repository or "",
            target_branch=request.target_branch or "main",
        ),
        commit=CommitContext(
            commit=request.commit,
            base_commit=request.base_commit,
            head_commit=request.head_commit,
        ),
        run=RunContext(
            run_id=request.run_id,
            timestamp=request.timestamp,
            job_id=None,
        ),
    )


def run_pipeline(
    request: PipelineRequest,
    registry: DeterministicAgentRegistry | None = None,
) -> PipelineState:
    use_adk_runtime = request.use_adk_runtime
    if use_adk_runtime is None:
        use_adk_runtime = bool(find_spec("google.adk"))

    if use_adk_runtime and not request.fail_fast:
        try:
            return _run_pipeline_with_adk(request=request, registry=registry)
        except Exception:
            # Fall back to deterministic local orchestration if ADK runtime fails.
            pass

    return _run_pipeline_local(request=request, registry=registry)


def _run_pipeline_local(
    request: PipelineRequest,
    registry: DeterministicAgentRegistry | None = None,
) -> PipelineState:
    active_registry = registry or build_default_registry()
    state = PipelineState(request=request, config=resolve_pipeline_config(request))

    for name in active_registry.resolve_order():
        state.execution_order.append(name)
        registration = active_registry.get(name)
        blocked_by = _blocked_dependencies(registration=registration, state=state)
        if blocked_by:
            output = {
                "status": "skipped",
                "reason": "dependency_failed",
                "blocked_by": blocked_by,
            }
            state.agent_outputs[name] = output
            state.shared[name] = output
            state.agent_status[name] = "skipped"
            continue

        try:
            output = registration.handler(state)
        except Exception as exc:
            failure = {
                "agent": name,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            state.failures.append(failure)
            output = {"status": "failed", "error": failure}
            state.agent_outputs[name] = output
            state.shared[name] = output
            state.agent_status[name] = "failed"
            if request.fail_fast:
                raise OrchestrationError(
                    f"Pipeline failed in agent '{name}': {type(exc).__name__}: {exc}"
                ) from exc
            continue

        state.agent_outputs[name] = output
        state.shared[name] = output
        state.agent_status[name] = "completed"

    if state.failures:
        completed_count = sum(1 for status in state.agent_status.values() if status == "completed")
        state.pipeline_status = "partial" if completed_count else "failed"
    else:
        state.pipeline_status = "completed"

    return state


STATE_AGENT_OUTPUTS = "__ci_rootcause_agent_outputs"
STATE_SHARED = "__ci_rootcause_shared"
STATE_EXECUTION_ORDER = "__ci_rootcause_execution_order"
STATE_AGENT_STATUS = "__ci_rootcause_agent_status"
STATE_FAILURES = "__ci_rootcause_failures"


def _run_pipeline_with_adk(
    request: PipelineRequest,
    registry: DeterministicAgentRegistry | None = None,
) -> PipelineState:
    # Import ADK modules lazily to keep local deterministic runtime independent.
    import asyncio

    from google.adk import Runner
    from google.adk.agents import BaseAgent, InvocationContext, SequentialAgent
    from google.adk.events import Event
    from google.adk.events.event_actions import EventActions
    from google.adk.runners import InMemorySessionService
    from google.genai import types

    active_registry = registry or build_default_registry()
    config = resolve_pipeline_config(request)

    class DeterministicADKAgent(BaseAgent):
        registration: AgentRegistration
        request: PipelineRequest
        config: PipelineConfig

        async def _run_async_impl(self, ctx: InvocationContext):
            state = ctx.session.state
            agent_outputs = deepcopy(state.get(STATE_AGENT_OUTPUTS, {}))
            shared = deepcopy(state.get(STATE_SHARED, {}))
            execution_order = list(state.get(STATE_EXECUTION_ORDER, []))
            agent_status = deepcopy(state.get(STATE_AGENT_STATUS, {}))
            failures = deepcopy(state.get(STATE_FAILURES, []))

            name = self.registration.name
            execution_order.append(name)

            blocked_by = _blocked_dependencies(registration=self.registration, state=PipelineState(
                request=self.request,
                shared=shared,
                agent_outputs=agent_outputs,
                execution_order=execution_order,
                agent_status=agent_status,
                failures=failures,
                config=self.config,
            ))

            if blocked_by:
                output = {
                    "status": "skipped",
                    "reason": "dependency_failed",
                    "blocked_by": blocked_by,
                }
                agent_outputs[name] = output
                shared[name] = output
                agent_status[name] = "skipped"
            else:
                try:
                    output = self.registration.handler(
                        PipelineState(
                            request=self.request,
                            shared=shared,
                            agent_outputs=agent_outputs,
                            execution_order=execution_order,
                            agent_status=agent_status,
                            failures=failures,
                            config=self.config,
                        )
                    )
                    agent_outputs[name] = output
                    shared[name] = output
                    agent_status[name] = "completed"
                except Exception as exc:
                    failure = {
                        "agent": name,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                    failures.append(failure)
                    output = {"status": "failed", "error": failure}
                    agent_outputs[name] = output
                    shared[name] = output
                    agent_status[name] = "failed"

            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                actions=EventActions(
                    state_delta={
                        STATE_AGENT_OUTPUTS: agent_outputs,
                        STATE_SHARED: shared,
                        STATE_EXECUTION_ORDER: execution_order,
                        STATE_AGENT_STATUS: agent_status,
                        STATE_FAILURES: failures,
                    }
                ),
            )

    async def _execute() -> dict[str, Any]:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="ci-rootcause",
            user_id="ci-rootcause",
            session_id=request.run_id or "run",
        )

        sub_agents = [
            DeterministicADKAgent(
                name=registration.name,
                registration=registration,
                request=request,
                config=config,
            )
            for registration in (
                active_registry.get(name) for name in active_registry.resolve_order()
            )
        ]

        root = SequentialAgent(
            name="ci_rootcause_pipeline",
            sub_agents=sub_agents,
        )
        runner = Runner(
            app_name="ci-rootcause",
            agent=root,
            session_service=session_service,
        )

        user_message = types.Content(
            role="user",
            parts=[types.Part(text="run ci-rootcause pipeline")],
        )
        async for _ in runner.run_async(
            user_id="ci-rootcause",
            session_id=request.run_id or "run",
            new_message=user_message,
        ):
            pass

        session = await session_service.get_session(
            app_name="ci-rootcause",
            user_id="ci-rootcause",
            session_id=request.run_id or "run",
        )
        return dict(session.state)

    session_state = asyncio.run(_execute())

    state = PipelineState(
        request=request,
        shared=deepcopy(session_state.get(STATE_SHARED, {})),
        agent_outputs=deepcopy(session_state.get(STATE_AGENT_OUTPUTS, {})),
        execution_order=list(session_state.get(STATE_EXECUTION_ORDER, [])),
        agent_status=deepcopy(session_state.get(STATE_AGENT_STATUS, {})),
        failures=deepcopy(session_state.get(STATE_FAILURES, [])),
        config=config,
    )

    if state.failures:
        completed_count = sum(1 for status in state.agent_status.values() if status == "completed")
        state.pipeline_status = "partial" if completed_count else "failed"
    else:
        state.pipeline_status = "completed"

    return state
