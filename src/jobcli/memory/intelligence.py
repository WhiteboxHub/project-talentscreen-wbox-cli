"""Optimization intelligence system.

Uses application memory to provide recommendations and optimize future applications.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .application_memory import (
    ApplicationMemory,
    ApplicationRecord,
    ApplicationStatus,
    RejectionReason,
)


class Recommendation(BaseModel):
    """Recommendation for improving applications."""

    recommendation_type: str
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    priority: str  # high, medium, low
    evidence: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)


class OpportunityScore(BaseModel):
    """Score for an application opportunity."""

    company_id: str
    company_name: str
    score: float = Field(ge=0.0, le=1.0)
    reasoning: List[str] = Field(default_factory=list)

    # Factors
    historical_success_rate: Optional[float] = None
    response_speed: Optional[str] = None  # fast, slow
    rejection_likelihood: Optional[float] = None


class OptimizationIntelligence:
    """Provides optimization recommendations based on application memory."""

    def __init__(self, memory: ApplicationMemory):
        """Initialize intelligence system.

        Args:
            memory: ApplicationMemory instance
        """
        self.memory = memory

    def get_recommendations(self) -> List[Recommendation]:
        """Get optimization recommendations.

        Returns:
            List of Recommendations
        """
        recommendations = []

        # Resume recommendations
        recommendations.extend(self._analyze_resume_effectiveness())

        # Question answer recommendations
        recommendations.extend(self._analyze_answer_patterns())

        # Timing recommendations
        recommendations.extend(self._analyze_response_times())

        # Rejection trend recommendations
        recommendations.extend(self._analyze_rejection_trends())

        # Company targeting recommendations
        recommendations.extend(self._analyze_company_targeting())

        # Sort by priority and confidence
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(
            key=lambda r: (priority_order.get(r.priority, 3), -r.confidence)
        )

        return recommendations

    def score_opportunity(
        self,
        company_name: str,
        position_title: str,
        ats_type: Optional[str] = None,
    ) -> OpportunityScore:
        """Score an application opportunity.

        Args:
            company_name: Company name
            position_title: Position title
            ats_type: ATS type

        Returns:
            OpportunityScore
        """
        company_id = self.memory._normalize_company_id(company_name)
        company_history = self.memory.get_company_insights(company_id)

        reasoning = []
        score_factors = []

        # Factor 1: Historical success with this company
        if company_history:
            if company_history.callback_rate > 0.5:
                reasoning.append(
                    f"High callback rate ({company_history.callback_rate:.0%}) with {company_name}"
                )
                score_factors.append(0.3)
            elif company_history.callback_rate > 0:
                reasoning.append(
                    f"Moderate callback rate ({company_history.callback_rate:.0%})"
                )
                score_factors.append(0.15)
            else:
                reasoning.append(f"No previous callbacks from {company_name}")
                score_factors.append(0.05)

            # Response speed
            if company_history.average_response_time_days:
                if company_history.average_response_time_days < 7:
                    reasoning.append("Fast response time (< 1 week)")
                    score_factors.append(0.1)
                elif company_history.average_response_time_days < 14:
                    reasoning.append("Moderate response time (1-2 weeks)")
                    score_factors.append(0.05)
        else:
            reasoning.append(f"No previous applications to {company_name}")
            score_factors.append(0.1)  # Neutral for new companies

        # Factor 2: Resume match
        best_resume = self.memory.get_best_resume_for_role(position_title)
        if best_resume and best_resume.callback_rate > 0.3:
            reasoning.append(
                f"Strong resume variant available ({best_resume.callback_rate:.0%} callback rate)"
            )
            score_factors.append(0.2)
        elif best_resume:
            reasoning.append("Relevant resume variant available")
            score_factors.append(0.1)

        # Factor 3: Overall callback rate
        overall_rate = self.memory.get_callback_rate()
        if overall_rate > 0.3:
            score_factors.append(0.2)
        elif overall_rate > 0.1:
            score_factors.append(0.1)

        # Factor 4: ATS familiarity
        if ats_type:
            ats_patterns = self.memory.get_ats_patterns(ats_type)
            if len(ats_patterns) > 10:
                reasoning.append(f"Familiar with {ats_type} ATS")
                score_factors.append(0.1)

        # Calculate score
        score = sum(score_factors)

        return OpportunityScore(
            company_id=company_id,
            company_name=company_name,
            score=score,
            reasoning=reasoning,
            historical_success_rate=company_history.callback_rate if company_history else None,
            response_speed="fast"
            if company_history
            and company_history.average_response_time_days
            and company_history.average_response_time_days < 7
            else "slow",
        )

    def suggest_answer(
        self,
        question_text: str,
        company_name: Optional[str] = None,
        ats_type: Optional[str] = None,
    ) -> Optional[str]:
        """Suggest answer to a question.

        Args:
            question_text: Question text
            company_name: Company name
            ats_type: ATS type

        Returns:
            Suggested answer or None
        """
        company_id = (
            self.memory._normalize_company_id(company_name) if company_name else None
        )

        similar = self.memory.get_similar_answers(
            question_text, company_id, ats_type, limit=1
        )

        if similar and similar[0].confidence > 0.5:
            return similar[0].answer

        return None

    def get_rejection_insights(self) -> Dict[str, Any]:
        """Get insights from rejection trends.

        Returns:
            Dict with insights
        """
        trends = self.memory.get_rejection_trends()

        if trends["total_rejections"] == 0:
            return {"insights": ["Not enough rejection data yet"]}

        insights = []

        # Analyze top reason
        if trends.get("top_reason"):
            top_reason = trends["top_reason"]
            top_count = trends["by_reason"].get(top_reason, 0)
            total = trends["total_rejections"]

            if top_count / total > 0.5:
                insights.append(
                    f"Primary rejection reason: {top_reason} ({top_count}/{total})"
                )

                # Provide specific advice
                if top_reason == "qualifications":
                    insights.append(
                        "Consider targeting positions closer to your experience level"
                    )
                elif top_reason == "experience":
                    insights.append(
                        "Highlight relevant projects and transferable skills"
                    )
                elif top_reason == "location":
                    insights.append(
                        "Focus on remote positions or local opportunities"
                    )
                elif top_reason == "salary":
                    insights.append(
                        "Research salary ranges before applying"
                    )

        # Ghosting rate
        ghosted_count = trends["by_reason"].get("ghosted", 0)
        if ghosted_count / trends["total_rejections"] > 0.3:
            insights.append(
                f"High ghosting rate ({ghosted_count} applications) - consider following up"
            )

        return {"insights": insights, "trends": trends}

    # ── Private Analysis Methods ──────────────────────────────────────────────

    def _analyze_resume_effectiveness(self) -> List[Recommendation]:
        """Analyze resume variant effectiveness."""
        recommendations = []

        variants = list(self.memory.resume_variants.values())

        if not variants:
            return recommendations

        # Find best performing variant
        variants_with_apps = [v for v in variants if v.applications_count > 3]

        if variants_with_apps:
            best = max(variants_with_apps, key=lambda v: v.callback_rate)
            worst = min(variants_with_apps, key=lambda v: v.callback_rate)

            if best.callback_rate > worst.callback_rate * 1.5:
                recommendations.append(
                    Recommendation(
                        recommendation_type="resume",
                        title="Use High-Performing Resume Variant",
                        description=f"Resume '{best.variant_name}' has {best.callback_rate:.0%} callback rate vs. '{worst.variant_name}' at {worst.callback_rate:.0%}",
                        confidence=0.8,
                        priority="high",
                        evidence=[
                            f"{best.variant_name}: {best.callbacks_count}/{best.applications_count} callbacks",
                            f"{worst.variant_name}: {worst.callbacks_count}/{worst.applications_count} callbacks",
                        ],
                        action_items=[
                            f"Use '{best.variant_name}' for similar roles",
                            f"Review what makes '{best.variant_name}' more effective",
                        ],
                    )
                )

        return recommendations

    def _analyze_answer_patterns(self) -> List[Recommendation]:
        """Analyze question answer patterns."""
        recommendations = []

        # Find questions with high reuse
        frequent_questions = [
            q for q in self.memory.questions.values() if q.times_used > 3
        ]

        if frequent_questions:
            # Check if any led to callbacks
            successful = [q for q in frequent_questions if q.led_to_callback]

            if successful:
                recommendations.append(
                    Recommendation(
                        recommendation_type="answers",
                        title="Reuse Successful Answers",
                        description=f"Found {len(successful)} answers that led to callbacks",
                        confidence=0.7,
                        priority="medium",
                        evidence=[
                            f"Answer to '{q.question_text[:50]}...' led to callback"
                            for q in successful[:3]
                        ],
                        action_items=[
                            "Save these answers as templates",
                            "Use similar phrasing for related questions",
                        ],
                    )
                )

        return recommendations

    def _analyze_response_times(self) -> List[Recommendation]:
        """Analyze response time patterns."""
        recommendations = []

        # Group applications by response time
        apps_with_callbacks = [
            app
            for app in self.memory.applications.values()
            if app.callback_received and app.callback_date
        ]

        if len(apps_with_callbacks) > 5:
            response_times = []
            for app in apps_with_callbacks:
                if app.callback_date:
                    delta = app.callback_date - app.applied_at
                    response_times.append(delta.days)

            avg_response = sum(response_times) / len(response_times)

            recommendations.append(
                Recommendation(
                    recommendation_type="timing",
                    title="Average Response Time",
                    description=f"Callbacks typically arrive within {avg_response:.0f} days",
                    confidence=0.6,
                    priority="low",
                    evidence=[
                        f"Analyzed {len(apps_with_callbacks)} successful applications",
                        f"Median response: {sorted(response_times)[len(response_times)//2]} days",
                    ],
                    action_items=[
                        "Follow up if no response after this period",
                        "Plan application pipeline accordingly",
                    ],
                )
            )

        return recommendations

    def _analyze_rejection_trends(self) -> List[Recommendation]:
        """Analyze rejection trend patterns."""
        recommendations = []

        trends = self.memory.get_rejection_trends()

        if trends["total_rejections"] < 3:
            return recommendations

        top_reason = trends.get("top_reason")
        if top_reason and trends["by_reason"].get(top_reason, 0) / trends[
            "total_rejections"
        ] > 0.4:

            advice_map = {
                "qualifications": "Target roles that match your qualifications more closely",
                "experience": "Emphasize transferable skills and relevant projects",
                "location": "Focus on remote positions or relocate",
                "salary": "Research market rates and adjust expectations",
            }

            if top_reason in advice_map:
                recommendations.append(
                    Recommendation(
                        recommendation_type="targeting",
                        title=f"Address Primary Rejection Reason: {top_reason}",
                        description=f"Most rejections ({trends['by_reason'][top_reason]}/{trends['total_rejections']}) due to {top_reason}",
                        confidence=0.75,
                        priority="high",
                        evidence=[
                            f"{reason}: {count} rejections"
                            for reason, count in trends["by_reason"].items()
                        ],
                        action_items=[advice_map[top_reason]],
                    )
                )

        return recommendations

    def _analyze_company_targeting(self) -> List[Recommendation]:
        """Analyze company targeting effectiveness."""
        recommendations = []

        # Find companies with high success rates
        high_success_companies = [
            c
            for c in self.memory.companies.values()
            if c.total_applications >= 2 and c.callback_rate > 0.5
        ]

        if high_success_companies:
            recommendations.append(
                Recommendation(
                    recommendation_type="targeting",
                    title="Focus on High-Success Companies",
                    description=f"Found {len(high_success_companies)} companies with >50% callback rate",
                    confidence=0.7,
                    priority="medium",
                    evidence=[
                        f"{c.company_name}: {c.callback_rate:.0%} callback rate"
                        for c in high_success_companies[:3]
                    ],
                    action_items=[
                        "Apply to more roles at these companies",
                        "Research what makes these companies a good fit",
                    ],
                )
            )

        # Find companies with consistent rejections
        consistent_rejections = [
            c
            for c in self.memory.companies.values()
            if c.total_applications >= 3 and c.callback_rate == 0
        ]

        if consistent_rejections:
            recommendations.append(
                Recommendation(
                    recommendation_type="targeting",
                    title="Avoid Low-Success Companies",
                    description=f"Found {len(consistent_rejections)} companies with 0% callback rate after multiple applications",
                    confidence=0.6,
                    priority="medium",
                    evidence=[
                        f"{c.company_name}: 0/{c.total_applications} callbacks"
                        for c in consistent_rejections[:3]
                    ],
                    action_items=[
                        "Focus efforts on other opportunities",
                        "Reassess fit with these companies",
                    ],
                )
            )

        return recommendations
