"""
Aviation Futures Intelligence Agent: Tracks and synthesises emerging aviation trends
to produce forecasts, scenario analyses, and adoption probability scores.
"""

import os
import re
import json
from datetime import datetime


def call_llm(prompt: str, role: str = "aviation_futures") -> str:
    """Call LLM. Falls back to mock if no API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM warning] Anthropic call failed: {e}. Using mock.")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
            )
            return response.choices[0].message.content
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM warning] OpenAI call failed: {e}. Using mock.")

    return _mock_llm_response(role, prompt)


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

DOMAINS = [
    "AI & autonomous flight",
    "eVTOL & urban air mobility",
    "drone logistics & last-mile delivery",
    "airport electrification & sustainable ground ops",
    "aerospace manufacturing & advanced materials",
    "military spillover technologies",
    "regulatory signals & airspace governance",
]

HORIZON_LABELS = {
    "near": "Near-term (1–3 years)",
    "mid": "Mid-term (3–7 years)",
    "far": "Far-term (7–15 years)",
}


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

def _mock_llm_response(role: str, prompt: str) -> str:
    """Return realistic mock Aviation Futures output."""
    # Route to the right mock based on role suffix
    if "scenario" in role:
        return _mock_scenario_analysis()
    if "domain_brief" in role:
        return _mock_domain_brief()
    return _mock_full_forecast()


def _mock_full_forecast() -> str:
    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "horizon": "mid",
        "executive_summary": (
            "The 2027–2031 window is the decisive inflection point for commercial aviation's "
            "technology stack. Three forces — regulatory maturation of autonomous systems, "
            "battery energy-density crossing the 400 Wh/kg threshold, and AI-driven air-traffic "
            "management — are converging faster than incumbents' procurement cycles can absorb. "
            "Operators who treat electrification and autonomy as separate programmes will be "
            "structurally disadvantaged by 2030."
        ),
        "domains": {
            "AI & autonomous flight": {
                "signal_strength": 8.4,
                "trend_direction": "accelerating",
                "key_developments": [
                    "FAA BEYOND programme expanding type-certification pathways for Level 4 autonomy",
                    "DARPA ACE dogfight victories accelerating transfer to commercial collision-avoidance",
                    "Honeywell and GE Aviation embedding transformer-architecture models in FMS units",
                ],
                "adoption_probability_score": 0.71,
                "adoption_note": "Probability of meaningful commercial deployment by 2030",
                "infrastructure_readiness": 0.52,
                "infrastructure_gaps": [
                    "Datalink bandwidth insufficient for dense-urban autonomous corridors",
                    "Liability framework for ML-assisted decisions absent in 14 of 20 ICAO contracting states",
                ],
                "watch_signals": [
                    "FAA Notice of Proposed Rulemaking on remote-ID for crewed aircraft",
                    "Airbus Wayfinder programme milestone announcements",
                ],
            },
            "eVTOL & urban air mobility": {
                "signal_strength": 7.9,
                "trend_direction": "maturing",
                "key_developments": [
                    "Joby Aviation type-certificate basis agreed; production ramp targeting 2026",
                    "Dubai AAM corridor operational — first sustained multi-operator market outside test zones",
                    "Battery swap infrastructure emerging as a competitive differentiator vs. in-situ charging",
                ],
                "adoption_probability_score": 0.58,
                "adoption_note": "Probability of mass-market (>500 routes globally) by 2031",
                "infrastructure_readiness": 0.41,
                "infrastructure_gaps": [
                    "Vertiport zoning stalled in 63% of US cities surveyed by GAMA (2024)",
                    "Grid capacity at existing heliport sites insufficient for simultaneous multi-aircraft charging",
                ],
                "watch_signals": [
                    "Archer Midnight certification timeline",
                    "EU U-Space Regulation enforcement commencement date",
                ],
            },
            "drone logistics & last-mile delivery": {
                "signal_strength": 8.1,
                "trend_direction": "accelerating",
                "key_developments": [
                    "Wing surpasses 1 million deliveries; unit economics approaching parity with van delivery in low-density suburban zones",
                    "FAA Part 108 BVLOS rulemaking expected Q3 2025 — the single largest regulatory unlock",
                    "Walmart / DroneUp expanding to 37 additional markets in 2025",
                ],
                "adoption_probability_score": 0.76,
                "adoption_note": "Probability of 10%+ last-mile share in served suburban markets by 2030",
                "infrastructure_readiness": 0.64,
                "infrastructure_gaps": [
                    "Noise ordinances blocking operations in the highest-density, highest-value urban cores",
                    "Interoperability standards for drone docking networks absent — vendor lock-in risk",
                ],
                "watch_signals": [
                    "FAA BVLOS final rule publication",
                    "Amazon Prime Air fleet utilisation rates post-UK launch",
                ],
            },
            "airport electrification & sustainable ground ops": {
                "signal_strength": 7.2,
                "trend_direction": "steady",
                "key_developments": [
                    "Heathrow all-electric airside vehicle mandate by 2030 — first major hub to commit",
                    "SAF blending mandates (EU 2% in 2025, 6% in 2030) reshaping fuel-infrastructure capex",
                    "Gate-to-gate hydrogen fuelling pilots at Amsterdam Schiphol and Toulouse Blagnac",
                ],
                "adoption_probability_score": 0.82,
                "adoption_note": "Probability of majority-electric ground fleets at top-50 global airports by 2035",
                "infrastructure_readiness": 0.69,
                "infrastructure_gaps": [
                    "Grid interconnect permitting averaging 7.4 years at US hub airports",
                    "SAF production capacity covers <4% of projected 2030 demand",
                ],
                "watch_signals": [
                    "US EPA finalisation of aviation greenhouse-gas emissions standards",
                    "IATA SAF Registry adoption rate",
                ],
            },
            "aerospace manufacturing & advanced materials": {
                "signal_strength": 7.6,
                "trend_direction": "accelerating",
                "key_developments": [
                    "Additive manufacturing now used in 14% of Boeing 787 components by count (up from 3% in 2020)",
                    "Thermoplastic composites enabling 40% faster fuselage assembly — Airbus A320 family retrofit programme",
                    "GKN Aerospace autonomous fibre-placement cells cutting skilled-labour requirement per kilo of structure by 60%",
                ],
                "adoption_probability_score": 0.68,
                "adoption_note": "Probability of digital-twin-closed-loop manufacturing standard at Tier-1 OEMs by 2030",
                "infrastructure_readiness": 0.73,
                "infrastructure_gaps": [
                    "MRO workforce skill gap — 3D-printing repair certification curriculum absent at most CAT-A schools",
                    "Supply-chain digital-twin data standards fragmented across Boeing, Airbus, and COMAC ecosystems",
                ],
                "watch_signals": [
                    "FAA AC 20-XXX additive manufacturing airworthiness advisory release",
                    "Boom Overture first-flight composite structure inspection results",
                ],
            },
            "military spillover technologies": {
                "signal_strength": 8.7,
                "trend_direction": "accelerating",
                "key_developments": [
                    "DARPA ALIAS cockpit-automation kit reaching TRL 7 — commercial derivative licencing discussions underway",
                    "AFRL directed-energy anti-drone systems now dual-use certified for airport perimeter protection",
                    "Link 16 waveform elements being incorporated into commercial ADS-B successor proposals",
                ],
                "adoption_probability_score": 0.63,
                "adoption_note": "Probability of at least three major military-derived technologies entering commercial certification by 2029",
                "infrastructure_readiness": 0.48,
                "infrastructure_gaps": [
                    "ITAR restrictions slowing allied-nation adoption of US-origin autonomy stacks",
                    "Civil certification reciprocity framework for dual-use avionics does not yet exist at EASA or CAAC",
                ],
                "watch_signals": [
                    "DoD OUSD(R&E) dual-use technology commercialisation policy update",
                    "NATO STANAG revisions covering autonomous-system interoperability",
                ],
            },
            "regulatory signals & airspace governance": {
                "signal_strength": 8.9,
                "trend_direction": "accelerating",
                "key_developments": [
                    "ICAO Assembly Resolution A43-1 commits member states to net-zero by 2050 — hardest governance signal in 30 years",
                    "FAA Reauthorisation Act 2024 mandates UAS traffic management (UTM) interoperability standard by 2026",
                    "EASA SC-VTOL amendment establishing stepped performance-based certification for novel configurations",
                ],
                "adoption_probability_score": None,
                "adoption_note": "Regulatory signals are leading indicators, not adoption metrics",
                "infrastructure_readiness": None,
                "infrastructure_gaps": [
                    "Divergence between FAA and EASA autonomous-operations frameworks creating dual-certification burden",
                    "Developing-nation CAA capacity gaps risking a two-speed global market",
                ],
                "watch_signals": [
                    "ICAO DRONE ENABLE programme Phase 3 outcome",
                    "FAA UTM interoperability standard final publication (deadline: Dec 2026)",
                ],
            },
        },
        "cross_domain_themes": [
            {
                "theme": "The autonomy–liability gap",
                "description": (
                    "Every domain's adoption ceiling is set by the same constraint: no mature legal framework "
                    "for algorithmic liability in safety-critical airspace operations. This is the single "
                    "highest-leverage policy problem across the entire sector."
                ),
                "affected_domains": ["AI & autonomous flight", "eVTOL & urban air mobility", "military spillover technologies"],
                "urgency": "high",
            },
            {
                "theme": "Grid-capacity as the silent bottleneck",
                "description": (
                    "Electrification narratives focus on vehicles and aircraft. The actual constraint is "
                    "distribution-grid capacity at airports, vertiports, and logistics hubs. Permitting "
                    "timelines are outrunning technology readiness by a factor of 2–3x."
                ),
                "affected_domains": ["eVTOL & urban air mobility", "airport electrification & sustainable ground ops", "drone logistics & last-mile delivery"],
                "urgency": "high",
            },
            {
                "theme": "Military-to-civil technology transfer acceleration",
                "description": (
                    "Post-Ukraine conflict investment in autonomous systems is generating the most rapid "
                    "dual-use technology pipeline since GPS. The civil aviation system is not institutionally "
                    "equipped to absorb this speed."
                ),
                "affected_domains": ["military spillover technologies", "AI & autonomous flight", "aerospace manufacturing & advanced materials"],
                "urgency": "medium",
            },
        ],
        "scenario_flags": [
            {
                "scenario": "Accelerated autonomy",
                "trigger": "FAA BVLOS final rule + one high-profile safe autonomous commercial operation",
                "probability": 0.34,
                "impact": "Compresses mid-term forecast into near-term; incumbent airlines face rapid competitive pressure",
            },
            {
                "scenario": "Regulatory retrenchment",
                "trigger": "Major eVTOL or drone accident with fatalities in a densely populated area",
                "probability": 0.22,
                "impact": "Delays mid-term adoption 3–5 years; shifts investment from operations to simulation and certification",
            },
            {
                "scenario": "Geopolitical fragmentation",
                "trigger": "CAAC or EASA unilateral standards that diverge irrecoverably from FAA framework",
                "probability": 0.29,
                "impact": "Creates three separate global markets; multiplies certification cost by 2.5–3x for OEMs",
            },
        ],
        "top_recommendations": [
            "Prioritise regulatory engagement over product development in any autonomy programme — the certification path IS the critical path.",
            "Model grid-capacity risk explicitly in all electrification business cases; do not treat it as a local-authority problem.",
            "Establish dual-use technology watch programmes covering DARPA, AFRL, and DSTL — the next 5 years of civil innovation will come from military pipelines.",
            "Design for ICAO net-zero compliance from day one; retrofitting is 3–5x more expensive than designing in.",
            "Treat UTM interoperability as a platform play, not a compliance checkbox — operators who own the data layer will own the market.",
        ],
    }
    return json.dumps(result, indent=2)


def _mock_domain_brief() -> str:
    result = {
        "domain": "eVTOL & urban air mobility",
        "signal_strength": 7.9,
        "trend_direction": "maturing",
        "horizon": "mid",
        "narrative": (
            "Urban air mobility is transitioning from demonstration to early commercialisation. "
            "The regulatory ceiling — long the primary constraint — is beginning to lift as EASA "
            "SC-VTOL and FAA G-1 issue papers establish repeatable certification pathways. The new "
            "bottleneck is infrastructure: vertiport permitting, grid interconnection, and noise "
            "ordinance variance processes are running 3–5 years behind aircraft readiness. Operators "
            "entering the market in 2025–2027 will effectively be building the infrastructure stack "
            "in parallel with the aircraft stack, doubling their capital requirements."
        ),
        "adoption_probability_score": 0.58,
        "infrastructure_readiness": 0.41,
        "key_developments": [
            "Joby Aviation type-certificate basis agreed; production ramp targeting 2026",
            "Dubai AAM corridor operational — first sustained multi-operator market outside test zones",
        ],
        "infrastructure_gaps": [
            "Vertiport zoning stalled in 63% of US cities surveyed by GAMA (2024)",
            "Grid capacity at existing heliport sites insufficient for simultaneous multi-aircraft charging",
        ],
        "watch_signals": [
            "Archer Midnight certification timeline",
            "EU U-Space Regulation enforcement commencement date",
        ],
    }
    return json.dumps(result, indent=2)


def _mock_scenario_analysis() -> str:
    result = {
        "scenarios": [
            {
                "name": "Accelerated Autonomy",
                "description": "FAA BVLOS rule lands early; a high-profile safe autonomous commercial delivery normalises public acceptance.",
                "probability": 0.34,
                "horizon_shift": "Compresses mid-term (3–7 yr) projections into near-term (1–3 yr) window.",
                "winners": ["Drone logistics operators", "AI avionics vendors", "UTM platform providers"],
                "losers": ["Traditional express couriers", "Slow-moving MRO chains without autonomy plans"],
                "infrastructure_implications": "UTM data infrastructure becomes critical path within 18 months.",
            },
            {
                "name": "Regulatory Retrenchment",
                "description": "Major eVTOL or drone accident with fatalities triggers 3–5 year moratorium on novel certifications.",
                "probability": 0.22,
                "horizon_shift": "Pushes mid-term adoption to far-term (7–15 yr).",
                "winners": ["Simulation and digital-twin vendors", "Conventional helicopter operators"],
                "losers": ["eVTOL OEMs with 2026–2028 commercial launch plans", "Early AAM corridor investors"],
                "infrastructure_implications": "Capital shifts from vertiport construction to simulator and certification-support facilities.",
            },
            {
                "name": "Geopolitical Fragmentation",
                "description": "CAAC and EASA standards diverge irrecoverably from FAA; three separate certification regimes emerge.",
                "probability": 0.29,
                "horizon_shift": "No horizon shift globally, but per-market timelines diverge significantly.",
                "winners": ["Regional champions in each bloc", "Dual-certification consultancies"],
                "losers": ["Global OEMs designing for single-cert", "Airlines operating mixed-nationality fleets"],
                "infrastructure_implications": "Data and communication infrastructure must be duplicated per regulatory bloc.",
            },
            {
                "name": "Technology Convergence",
                "description": "Battery density, AI reliability, and regulatory maturity hit thresholds simultaneously circa 2028.",
                "probability": 0.15,
                "horizon_shift": "Triggers non-linear adoption curve; forecasts from 2024–2026 become systematically low.",
                "winners": ["First-mover operators", "Airport infrastructure owners", "SAF producers (demand surge)"],
                "losers": ["Conservative incumbents who waited for 'proof'", "Fossil-fuel ground-support equipment makers"],
                "infrastructure_implications": "Grid and vertiport infrastructure faces acute demand shock; permitting bottleneck becomes critical constraint.",
            },
        ],
        "scenario_matrix_note": (
            "Scenarios are not mutually exclusive across domains. Accelerated Autonomy in drone logistics "
            "can co-exist with Regulatory Retrenchment in eVTOL. Monitor each domain's regulatory signal "
            "independently."
        ),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _load_template(name: str, fallback: str) -> str:
    prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
    path = os.path.join(prompts_dir, f"{name}.md")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return fallback


def _build_forecast_prompt(
    domains: list[str],
    horizon: str,
    focus_notes: str,
    context: str,
) -> str:
    template = _load_template(
        "aviation_futures",
        "You are an aviation futures intelligence analyst. {CONTEXT}\n\nDomains: {DOMAINS}\nHorizon: {HORIZON}\nFocus: {FOCUS_NOTES}\n\nReturn a comprehensive JSON forecast.",
    )
    prompt = template.replace("{CONTEXT}", context)
    prompt = prompt.replace("{DOMAINS}", "\n".join(f"- {d}" for d in domains))
    prompt = prompt.replace("{HORIZON}", HORIZON_LABELS.get(horizon, horizon))
    prompt = prompt.replace("{FOCUS_NOTES}", focus_notes or "No specific focus — cover all domains.")
    return prompt


def _build_domain_prompt(domain: str, horizon: str, context: str) -> str:
    template = _load_template(
        "aviation_futures",
        "You are an aviation futures intelligence analyst. Focus on the single domain: {DOMAIN}. {CONTEXT}\n\nHorizon: {HORIZON}\n\nReturn a focused JSON domain brief.",
    )
    all_domains = "\n".join(f"- {d}" for d in [domain])
    prompt = template.replace("{CONTEXT}", context)
    prompt = prompt.replace("{DOMAINS}", all_domains)
    prompt = prompt.replace("{HORIZON}", HORIZON_LABELS.get(horizon, horizon))
    prompt = prompt.replace("{FOCUS_NOTES}", f"Focus exclusively on: {domain}")
    return prompt


def _build_scenario_prompt(domains: list[str], context: str) -> str:
    template = _load_template(
        "aviation_futures",
        "You are an aviation futures intelligence analyst. {CONTEXT}\n\nDomains: {DOMAINS}\n\nGenerate scenario analyses with probabilities. Return JSON.",
    )
    prompt = template.replace("{CONTEXT}", context)
    prompt = prompt.replace("{DOMAINS}", "\n".join(f"- {d}" for d in domains))
    prompt = prompt.replace("{HORIZON}", "all horizons")
    prompt = prompt.replace("{FOCUS_NOTES}", "Generate scenario analyses — not domain forecasts.")
    prompt += "\n\nReturn ONLY a scenario analysis JSON with keys: scenarios (list), scenario_matrix_note (string)."
    return prompt


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def _parse_json_response(response: str, fallback: dict) -> dict:
    for extractor in [
        lambda r: json.loads(r),
        lambda r: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", r, re.DOTALL).group(1)),
        lambda r: json.loads(re.search(r"\{.*\}", r, re.DOTALL).group(0)),
    ]:
        try:
            return extractor(response)
        except Exception:
            continue
    return {**fallback, "parse_error": True, "raw": response[:500]}


# ---------------------------------------------------------------------------
# Public agent class
# ---------------------------------------------------------------------------

class AviationFuturesAgent:
    """
    Tracks and synthesises aviation technology trends across seven domains
    to produce forecasts, scenario analyses, and adoption probability scores.
    """

    def run_forecast(
        self,
        domains: list[str] | None = None,
        horizon: str = "mid",
        focus_notes: str = "",
        project_memory=None,
    ) -> dict:
        """
        Generate a full multi-domain aviation futures forecast.

        Args:
            domains: List of domain strings to cover; defaults to all seven.
            horizon: 'near' (1-3yr), 'mid' (3-7yr), or 'far' (7-15yr).
            focus_notes: Optional free-text directing the analysis.
            project_memory: Optional ProjectMemory for book-context grounding.

        Returns:
            dict with keys: executive_summary, domains, cross_domain_themes,
                            scenario_flags, top_recommendations, generated_at.
        """
        active_domains = domains or DOMAINS
        context = project_memory.get_context_for_agent() if project_memory else ""
        prompt = _build_forecast_prompt(active_domains, horizon, focus_notes, context)
        response = call_llm(prompt, role="aviation_futures_forecast")
        return _parse_json_response(
            response,
            {"executive_summary": "Parse error.", "domains": {}, "top_recommendations": []},
        )

    def run_domain_brief(
        self,
        domain: str,
        horizon: str = "mid",
        project_memory=None,
    ) -> dict:
        """
        Generate a focused brief for a single aviation domain.

        Returns:
            dict with keys: domain, signal_strength, trend_direction, narrative,
                            adoption_probability_score, infrastructure_readiness,
                            key_developments, infrastructure_gaps, watch_signals.
        """
        context = project_memory.get_context_for_agent() if project_memory else ""
        prompt = _build_domain_prompt(domain, horizon, context)
        response = call_llm(prompt, role="aviation_futures_domain_brief")
        return _parse_json_response(
            response,
            {"domain": domain, "narrative": "Parse error.", "watch_signals": []},
        )

    def run_scenario_analysis(
        self,
        domains: list[str] | None = None,
        project_memory=None,
    ) -> dict:
        """
        Generate scenario analyses across all domains.

        Returns:
            dict with keys: scenarios (list of scenario dicts), scenario_matrix_note.
        """
        active_domains = domains or DOMAINS
        context = project_memory.get_context_for_agent() if project_memory else ""
        prompt = _build_scenario_prompt(active_domains, context)
        response = call_llm(prompt, role="aviation_futures_scenario")
        return _parse_json_response(
            response,
            {"scenarios": [], "scenario_matrix_note": "Parse error."},
        )
