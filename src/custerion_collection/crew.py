from __future__ import annotations

from crewai import Agent, Crew, LLM, Process, Task

from custerion_collection.config import model_name, process_mode
from custerion_collection.tools import (
    curator_tools,
    follow_up_tools,
    historian_tools,
    industry_tools,
    technical_tools,
)


def _llm(role: str | None = None) -> LLM:
    return LLM(model=model_name(role=role))


def _process(process_mode_override: str | None = None) -> Process:
    mode = process_mode(override=process_mode_override)
    if mode == "sequential":
        return Process.sequential
    return Process.hierarchical


def build_deep_dive_crew(
    title: str,
    suggestion_mode: bool,
    process_mode_override: str | None = None,
) -> Crew:
    manager = Agent(
        role="Creative Director",
        goal="Plan and validate the deep-dive workflow for one film.",
        backstory="Experienced editor-manager coordinating film research teams.",
        llm=_llm(role="Creative Director"),
        verbose=False,
    )

    curator = Agent(
        role="Personal Matchmaker",
        goal="Frame why this film is relevant for this user now.",
        backstory="Taste analyst focused on viewing history and preference patterns.",
        llm=_llm(role="Personal Matchmaker"),
        tools=curator_tools(),
        verbose=False,
    )

    historian = Agent(
        role="Cultural Historian",
        goal="Extract historical and critical context.",
        backstory="Film scholar specializing in context and canon evolution.",
        llm=_llm(role="Cultural Historian"),
        tools=historian_tools(),
        verbose=False,
    )

    technical = Agent(
        role="Technical Director",
        goal="Analyze craft decisions and film language.",
        backstory="Craft specialist in cinematography, editing, and sound.",
        llm=_llm(role="Technical Director"),
        tools=technical_tools(),
        verbose=False,
    )

    industry = Agent(
        role="Industrial Analyst",
        goal="Explain production, release, and market impact.",
        backstory="Industry analyst focused on economics and distribution.",
        llm=_llm(role="Industrial Analyst"),
        tools=industry_tools(),
        verbose=False,
    )

    follow_up = Agent(
        role="Follow-Up Curator",
        goal="Curate optional high-signal links for deeper exploration.",
        backstory="Curator balancing relevance, quality, and diversity of sources.",
        llm=_llm(role="Follow-Up Curator"),
        tools=follow_up_tools(),
        verbose=False,
    )

    editor = Agent(
        role="Script Editor",
        goal="Produce a single coherent narrative with confidence disclosures.",
        backstory="Senior editor who turns research into clear guided tours.",
        llm=_llm(role="Script Editor"),
        verbose=False,
    )

    intake_text = "system suggestion mode" if suggestion_mode else "explicit title mode"

    planning = Task(
        description=(
            "Define section plan and evidence requirements for a deep-dive on "
            f"'{title}' in {intake_text}."
        ),
        expected_output=(
            "A concise plan with sections, required evidence, acceptance checks, and explicit no-speculation rules."
        ),
        agent=editor,
    )

    personalization = Task(
        description=(
            f"Write a short personalized framing for '{title}' and identify recommendation angles."
        ),
        expected_output="A personalized intro and recommendation rationale bullets.",
        agent=curator,
        context=[planning],
    )

    history = Task(
        description=(
            f"Produce historical and critical context findings for '{title}'. "
            "Do not infer facts that are not supported by tool outputs."
        ),
        expected_output="Structured notes with confidence and citations; mark unknowns when evidence is missing.",
        agent=historian,
        context=[planning],
    )

    craft = Task(
        description=(
            f"Produce craft and technical findings for '{title}'. "
            "Do not infer facts that are not supported by tool outputs."
        ),
        expected_output="Structured technical notes with confidence and citations; mark unknowns when evidence is missing.",
        agent=technical,
        context=[planning],
    )

    market = Task(
        description=(
            f"Produce production and market impact findings for '{title}'. "
            "Do not infer facts that are not supported by tool outputs."
        ),
        expected_output="Industry notes with confidence and citations; mark unknowns when evidence is missing.",
        agent=industry,
        context=[planning],
    )

    links = Task(
        description=(
            f"Curate 5 to 8 follow-up media items for '{title}' with a max of 3 per type."
        ),
        expected_output="A bounded list of links with one-sentence rationale and confidence.",
        agent=follow_up,
        context=[history, craft, market],
    )

    synthesis = Task(
        description=(
            "Synthesize final deep-dive in one voice. Include known unknowns, watch-next list, "
            "confidence markers, and follow-up media appendix. Never invent facts; if unsupported, state insufficient evidence."
        ),
        expected_output="Final deep-dive markdown with source references.",
        agent=editor,
        context=[personalization, history, craft, market, links],
    )

    return Crew(
        agents=[curator, historian, technical, industry, follow_up, editor],
        tasks=[planning, personalization, history, craft, market, links, synthesis],
        process=_process(process_mode_override=process_mode_override),
        manager_agent=manager,
        verbose=True,
    )
