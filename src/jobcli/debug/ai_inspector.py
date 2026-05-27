"""AI reasoning inspector for debugging LLM decisions.

Captures and analyzes AI reasoning for field detection, classification, and actions.
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AITaskType(str, Enum):
    """Types of AI tasks."""

    FIELD_DETECTION = "field_detection"
    FIELD_CLASSIFICATION = "field_classification"
    SELECTOR_GENERATION = "selector_generation"
    VALUE_EXTRACTION = "value_extraction"
    ANSWER_GENERATION = "answer_generation"
    ERROR_DIAGNOSIS = "error_diagnosis"


class AIReasoning(BaseModel):
    """AI reasoning for a single decision.

    Captures prompt, response, confidence, and decision metadata.
    """

    reasoning_id: str = Field(..., description="Unique reasoning ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    task_type: AITaskType = Field(..., description="Type of AI task")

    # Input
    prompt: str = Field(..., description="Prompt sent to LLM")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (page HTML, prior decisions, etc.)",
    )

    # Output
    response: str = Field(..., description="Raw LLM response")
    parsed_output: Optional[Dict[str, Any]] = Field(
        None, description="Parsed structured output"
    )

    # Decision
    decision: str = Field(..., description="Final decision made")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    reasoning_steps: List[str] = Field(
        default_factory=list, description="Chain of reasoning steps"
    )

    # Metadata
    model: str = Field(..., description="LLM model used")
    temperature: float = Field(0.0, description="Temperature used")
    tokens_used: Optional[int] = Field(None, description="Tokens consumed")
    latency_ms: int = Field(0, description="LLM call latency")

    # Validation
    validated: Optional[bool] = Field(None, description="Was decision validated?")
    validation_result: Optional[str] = Field(None, description="Validation outcome")
    ground_truth: Optional[str] = Field(
        None, description="Ground truth (if known, for calibration)"
    )
    correct: Optional[bool] = Field(None, description="Was decision correct?")


class AIInspector:
    """Inspector for AI reasoning and decisions."""

    def __init__(self):
        """Initialize AI inspector."""
        self.reasonings: List[AIReasoning] = []
        self._reasoning_counter = 0

    def record_reasoning(
        self,
        task_type: AITaskType,
        prompt: str,
        response: str,
        decision: str,
        confidence: float,
        model: str,
        context: Optional[Dict[str, Any]] = None,
        parsed_output: Optional[Dict[str, Any]] = None,
        reasoning_steps: Optional[List[str]] = None,
        temperature: float = 0.0,
        tokens_used: Optional[int] = None,
        latency_ms: int = 0,
    ) -> AIReasoning:
        """Record an AI reasoning instance.

        Args:
            task_type: Type of AI task
            prompt: Prompt sent to LLM
            response: Raw LLM response
            decision: Final decision made
            confidence: Confidence score [0.0, 1.0]
            model: LLM model used
            context: Additional context
            parsed_output: Parsed structured output
            reasoning_steps: Chain of reasoning steps
            temperature: Temperature used
            tokens_used: Tokens consumed
            latency_ms: LLM call latency

        Returns:
            Created AIReasoning instance
        """
        self._reasoning_counter += 1
        reasoning_id = f"reasoning_{self._reasoning_counter:04d}"

        reasoning = AIReasoning(
            reasoning_id=reasoning_id,
            task_type=task_type,
            prompt=prompt,
            response=response,
            decision=decision,
            confidence=confidence,
            model=model,
            context=context or {},
            parsed_output=parsed_output,
            reasoning_steps=reasoning_steps or [],
            temperature=temperature,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

        self.reasonings.append(reasoning)
        return reasoning

    def validate_reasoning(
        self,
        reasoning_id: str,
        validation_result: str,
        correct: bool,
        ground_truth: Optional[str] = None,
    ) -> None:
        """Validate an AI reasoning after execution.

        Args:
            reasoning_id: Reasoning to validate
            validation_result: Validation outcome description
            correct: Was the decision correct?
            ground_truth: Ground truth value (if known)
        """
        reasoning = self.get_reasoning(reasoning_id)
        if reasoning:
            reasoning.validated = True
            reasoning.validation_result = validation_result
            reasoning.correct = correct
            reasoning.ground_truth = ground_truth

    def get_reasoning(self, reasoning_id: str) -> Optional[AIReasoning]:
        """Get reasoning by ID.

        Args:
            reasoning_id: Reasoning ID

        Returns:
            AIReasoning or None
        """
        for r in self.reasonings:
            if r.reasoning_id == reasoning_id:
                return r
        return None

    def get_reasonings_by_task(self, task_type: AITaskType) -> List[AIReasoning]:
        """Get all reasonings for a task type.

        Args:
            task_type: Task type to filter

        Returns:
            List of matching reasonings
        """
        return [r for r in self.reasonings if r.task_type == task_type]

    def get_failed_reasonings(self) -> List[AIReasoning]:
        """Get reasonings that were validated as incorrect.

        Returns:
            List of incorrect reasonings
        """
        return [r for r in self.reasonings if r.validated and not r.correct]

    def get_confidence_calibration(self) -> Dict[str, Any]:
        """Analyze confidence calibration.

        Returns:
            Calibration statistics showing if confidence matches accuracy
        """
        validated = [r for r in self.reasonings if r.validated is not None]

        if not validated:
            return {
                "total_validated": 0,
                "calibration": {},
            }

        # Group by confidence buckets
        buckets = {
            "high (≥0.8)": [r for r in validated if r.confidence >= 0.8],
            "medium (0.6-0.8)": [r for r in validated if 0.6 <= r.confidence < 0.8],
            "low (<0.6)": [r for r in validated if r.confidence < 0.6],
        }

        calibration = {}
        for bucket_name, bucket_reasonings in buckets.items():
            if bucket_reasonings:
                correct_count = sum(1 for r in bucket_reasonings if r.correct)
                accuracy = correct_count / len(bucket_reasonings)
                avg_confidence = sum(r.confidence for r in bucket_reasonings) / len(
                    bucket_reasonings
                )

                calibration[bucket_name] = {
                    "count": len(bucket_reasonings),
                    "accuracy": accuracy,
                    "avg_confidence": avg_confidence,
                    "calibration_error": abs(avg_confidence - accuracy),
                }

        return {
            "total_validated": len(validated),
            "calibration": calibration,
        }

    def get_task_performance(self) -> Dict[AITaskType, Dict[str, Any]]:
        """Get performance metrics per task type.

        Returns:
            Dict of {task_type: {accuracy, avg_confidence, count}}
        """
        performance = {}

        for task_type in AITaskType:
            task_reasonings = self.get_reasonings_by_task(task_type)
            validated = [r for r in task_reasonings if r.validated is not None]

            if validated:
                correct_count = sum(1 for r in validated if r.correct)
                accuracy = correct_count / len(validated)
                avg_confidence = sum(r.confidence for r in validated) / len(validated)
                avg_latency = sum(r.latency_ms for r in task_reasonings) / len(
                    task_reasonings
                )

                performance[task_type] = {
                    "total_count": len(task_reasonings),
                    "validated_count": len(validated),
                    "accuracy": accuracy,
                    "avg_confidence": avg_confidence,
                    "avg_latency_ms": avg_latency,
                }

        return performance

    def print_reasoning(self, reasoning_id: str) -> None:
        """Print detailed reasoning to console.

        Args:
            reasoning_id: Reasoning ID to print
        """
        reasoning = self.get_reasoning(reasoning_id)
        if not reasoning:
            print(f"Reasoning {reasoning_id} not found")
            return

        print("\n" + "=" * 70)
        print(f"AI REASONING: {reasoning.reasoning_id}")
        print("=" * 70)
        print(f"Task: {reasoning.task_type.value}")
        print(f"Model: {reasoning.model} (temp={reasoning.temperature})")
        print(f"Timestamp: {reasoning.timestamp}")
        print(f"Latency: {reasoning.latency_ms}ms")
        if reasoning.tokens_used:
            print(f"Tokens: {reasoning.tokens_used}")

        print("\n--- PROMPT ---")
        print(reasoning.prompt[:500])
        if len(reasoning.prompt) > 500:
            print(f"... ({len(reasoning.prompt) - 500} more chars)")

        print("\n--- RESPONSE ---")
        print(reasoning.response[:500])
        if len(reasoning.response) > 500:
            print(f"... ({len(reasoning.response) - 500} more chars)")

        print("\n--- DECISION ---")
        print(f"Decision: {reasoning.decision}")
        print(f"Confidence: {reasoning.confidence:.2%}")

        if reasoning.reasoning_steps:
            print("\n--- REASONING STEPS ---")
            for i, step in enumerate(reasoning.reasoning_steps, 1):
                print(f"{i}. {step}")

        if reasoning.validated is not None:
            print("\n--- VALIDATION ---")
            print(f"Correct: {'✓' if reasoning.correct else '✗'}")
            print(f"Result: {reasoning.validation_result}")
            if reasoning.ground_truth:
                print(f"Ground Truth: {reasoning.ground_truth}")

        print("=" * 70)

    def export_reasonings(self, output_path: Path) -> None:
        """Export all reasonings to JSON file.

        Args:
            output_path: Path to save reasonings
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "total_reasonings": len(self.reasonings),
            "confidence_calibration": self.get_confidence_calibration(),
            "task_performance": {
                k.value: v for k, v in self.get_task_performance().items()
            },
            "reasonings": [r.model_dump() for r in self.reasonings],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def generate_calibration_report(self) -> str:
        """Generate confidence calibration report.

        Returns:
            Human-readable calibration report
        """
        calibration = self.get_confidence_calibration()

        report = "\n" + "=" * 70 + "\n"
        report += "AI CONFIDENCE CALIBRATION REPORT\n"
        report += "=" * 70 + "\n"

        if calibration["total_validated"] == 0:
            report += "No validated reasonings yet.\n"
            return report

        report += f"Total Validated: {calibration['total_validated']}\n\n"

        for bucket_name, stats in calibration["calibration"].items():
            report += f"{bucket_name}:\n"
            report += f"  Count: {stats['count']}\n"
            report += f"  Accuracy: {stats['accuracy']:.2%}\n"
            report += f"  Avg Confidence: {stats['avg_confidence']:.2%}\n"
            report += f"  Calibration Error: {stats['calibration_error']:.2%}\n"

            # Diagnosis
            if stats["calibration_error"] > 0.15:
                if stats["avg_confidence"] > stats["accuracy"]:
                    report += "  ⚠ Overconfident (reduce confidence)\n"
                else:
                    report += "  ⚠ Underconfident (increase confidence)\n"
            else:
                report += "  ✓ Well calibrated\n"

            report += "\n"

        report += "=" * 70 + "\n"

        return report

    def generate_task_performance_report(self) -> str:
        """Generate task performance report.

        Returns:
            Human-readable performance report
        """
        performance = self.get_task_performance()

        report = "\n" + "=" * 70 + "\n"
        report += "AI TASK PERFORMANCE REPORT\n"
        report += "=" * 70 + "\n"

        if not performance:
            report += "No task data yet.\n"
            return report

        for task_type, stats in performance.items():
            report += f"\n{task_type.value}:\n"
            report += f"  Total: {stats['total_count']}\n"
            report += f"  Validated: {stats['validated_count']}\n"

            if stats["validated_count"] > 0:
                report += f"  Accuracy: {stats['accuracy']:.2%}\n"
                report += f"  Avg Confidence: {stats['avg_confidence']:.2%}\n"
            else:
                report += "  (No validation data)\n"

            report += f"  Avg Latency: {stats['avg_latency_ms']:.0f}ms\n"

        report += "\n" + "=" * 70 + "\n"

        return report


# Global AI inspector instance
_global_inspector = AIInspector()


def get_ai_inspector() -> AIInspector:
    """Get global AI inspector instance."""
    return _global_inspector
