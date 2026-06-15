"""
Orchestrator: runs all six ordinance agents in sequence and assembles the session.
"""

from .classification_agent import ClassificationAgent
from .definitions_agent import DefinitionsAgent
from .zoning_agent import ZoningAgent
from .setback_agent import SetbackAgent
from .pathways_agent import PathwaysAgent
from .environmental_agent import EnvironmentalAgent


class OrdinanceOrchestrator:
    """Runs all six agents in dependency order and populates the session."""

    def run(self, session, progress_callback=None) -> None:
        """
        progress_callback(step: int, total: int, label: str) — optional UI hook.
        """
        total = 6
        inputs = session.inputs

        def _step(n, label):
            if progress_callback:
                progress_callback(n, total, label)

        # 1. Tier classification (everything downstream depends on tier)
        _step(1, "Classifying facility tier...")
        tier_result = ClassificationAgent().classify(inputs)
        session.set_output("tier_classification", tier_result)
        tier = tier_result.get("tier", 2)

        # 2. Use definitions
        _step(2, "Generating use definitions...")
        defs_result = DefinitionsAgent().generate(inputs, tier)
        session.set_output("use_definitions", defs_result)

        # 3. Zoning language
        _step(3, "Drafting zoning language...")
        zoning_result = ZoningAgent().generate(inputs, tier)
        session.set_output("zoning_language", zoning_result)

        # 4. Setback recommendations
        _step(4, "Computing setback requirements...")
        setback_result = SetbackAgent().generate(inputs, tier)
        session.set_output("setback_recommendations", setback_result)

        # 5. Approval pathways
        _step(5, "Mapping approval pathways...")
        pathways_result = PathwaysAgent().generate(inputs, tier)
        session.set_output("approval_pathways", pathways_result)

        # 6. Environmental triggers
        _step(6, "Assessing environmental review triggers...")
        env_result = EnvironmentalAgent().generate(inputs, tier)
        session.set_output("environmental_triggers", env_result)
