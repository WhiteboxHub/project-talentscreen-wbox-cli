# Application Memory System

Intelligent memory that learns from every application to optimize future ones.

## Overview

The application memory system **tracks and learns from every application** to provide:

1. **Company History** - Track success rates, response times, rejection patterns per company
2. **Answer Reuse** - Save and suggest answers from similar questions
3. **Recruiter Interactions** - Remember contacts and communication patterns
4. **ATS Patterns** - Learn platform-specific quirks and successful strategies
5. **Resume Effectiveness** - Track which resume variants get callbacks
6. **Callback Analysis** - Understand timing and success patterns
7. **Rejection Intelligence** - Identify trends and adapt strategy

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ApplicationMemory                            │
│                                                                  │
│  Central storage for all application data                       │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ├──► applications.json
               │    • Complete application records
               │    • Status, answers, interactions
               │    • Outcomes and timing
               │
               ├──► companies.json
               │    • Company history
               │    • Callback rates, response times
               │    • Known recruiters
               │
               ├──► resume_variants.json
               │    • Resume versions
               │    • Effectiveness metrics
               │    • Targeting info
               │
               ├──► questions.json
               │    • Question/answer pairs
               │    • Usage count, confidence
               │    • Success correlation
               │
               └──► ats_patterns.json
                    • Platform-specific patterns
                    • Selector strategies
                    • Workflow quirks

                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                OptimizationIntelligence                         │
│                                                                  │
│  Analyzes memory to provide recommendations                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Application Memory

### Initialize Memory

```python
from jobcli.memory import ApplicationMemory
from pathlib import Path

# Initialize (creates storage directory)
memory = ApplicationMemory(
    memory_dir=Path("application_memory")
)
```

### Create Application

```python
app = memory.create_application(
    company_name="Google",
    position_title="Software Engineer",
    job_url="https://careers.google.com/job123",
    ats_type="greenhouse"
)

print(f"Application ID: {app.application_id}")
print(f"Company ID: {app.company_id}")
```

### Update Application Status

```python
# When submitted
memory.update_application(
    app.application_id,
    status="submitted",
    resume_variant_id="resume_v2"
)

# When callback received
memory.update_application(
    app.application_id,
    callback_received=True,
    callback_date=datetime.utcnow(),
    status="screening"
)

# When rejected
memory.update_application(
    app.application_id,
    rejection_received=True,
    rejection_date=datetime.utcnow(),
    rejection_reason="qualifications",
    rejection_details="Looking for 5+ years experience",
    status="rejected"
)
```

### Add Answers

```python
# Add answer to application
memory.add_answer(
    application_id=app.application_id,
    question_text="Why do you want to work here?",
    answer="I'm passionate about Google's mission to organize the world's information...",
    confidence=0.9,
    field_type="motivation"
)

# System automatically:
# - Indexes answer for future reuse
# - Tracks usage count
# - Associates with company and ATS
```

### Add Recruiter Interactions

```python
# Email from recruiter
memory.add_interaction(
    application_id=app.application_id,
    interaction_type="email",
    recruiter_name="Jane Smith",
    recruiter_email="jane.smith@google.com",
    sentiment="positive",
    notes="Interested in scheduling phone screen"
)

# Phone screen
memory.add_interaction(
    application_id=app.application_id,
    interaction_type="phone",
    recruiter_name="Jane Smith",
    sentiment="positive",
    notes="30 min phone screen, went well"
)
```

---

## 2. Resume Variants

### Add Resume Variant

```python
resume = memory.add_resume_variant(
    variant_name="Software Engineer - Backend Focus",
    file_path="/path/to/resume_backend.pdf",
    targeted_role="Software Engineer",
    targeted_industry="Tech",
    modifications=[
        "Emphasized Python and distributed systems",
        "Added database optimization projects",
        "Removed frontend experience section"
    ]
)

print(f"Variant ID: {resume.variant_id}")
```

### Track Resume Effectiveness

```python
# When using resume
app = memory.create_application(...)
memory.update_application(
    app.application_id,
    resume_variant_id=resume.variant_id
)

# When outcome known
if callback_received:
    memory.update_resume_effectiveness(
        resume.variant_id,
        callback=True
    )

if interview_scheduled:
    memory.update_resume_effectiveness(
        resume.variant_id,
        interview=True
    )

# System automatically calculates callback rate
print(f"Callback rate: {resume.callback_rate:.2%}")
```

### Get Best Resume for Role

```python
best = memory.get_best_resume_for_role("Software Engineer")

if best:
    print(f"Use: {best.variant_name}")
    print(f"Callback rate: {best.callback_rate:.2%}")
    print(f"Based on {best.applications_count} applications")
```

---

## 3. Company History

### Get Company Insights

```python
company = memory.get_company_insights("google")

if company:
    print(f"Total applications: {company.total_applications}")
    print(f"Callback rate: {company.callback_rate:.2%}")
    print(f"Avg response time: {company.average_response_time_days:.0f} days")
    
    print(f"\nKnown recruiters:")
    for recruiter in company.known_recruiters:
        print(f"  - {recruiter['name']} ({recruiter['email']})")
    
    print(f"\nCommon rejection reasons:")
    for reason in company.common_rejection_reasons:
        print(f"  - {reason.value}")
```

### Company History Structure

```python
CompanyHistory(
    company_id="google",
    company_name="Google",
    
    # Stats
    total_applications=5,
    callbacks_received=3,
    rejections_received=2,
    callback_rate=0.60,
    
    # Timing
    average_response_time_days=7.5,
    first_application=datetime(2025, 1, 1),
    last_application=datetime(2026, 5, 15),
    
    # Patterns
    preferred_ats="greenhouse",
    common_rejection_reasons=["qualifications", "experience"],
    known_recruiters=[
        {"name": "Jane Smith", "email": "jane@google.com"}
    ],
    
    # Insights
    best_resume_variant="resume_v2",
    successful_question_patterns=[...],
    notes="Responds quickly, prefers detailed technical answers"
)
```

---

## 4. Question Answering

### Get Similar Answers

```python
# When encountering a question
similar = memory.get_similar_answers(
    question_text="Why do you want to work at our company?",
    company_id="google",  # Optional: filter by company
    ats_type="greenhouse",  # Optional: filter by ATS
    limit=5
)

for qa in similar:
    print(f"Question: {qa.question_text}")
    print(f"Answer: {qa.answer}")
    print(f"Confidence: {qa.confidence:.2%}")
    print(f"Used {qa.times_used} times")
    if qa.led_to_callback:
        print("✓ Led to callback!")
```

### Question Answer Structure

```python
QuestionAnswer(
    question_id="abc123...",  # MD5 hash of normalized question
    question_text="Why do you want to work here?",
    answer="I'm passionate about...",
    confidence=0.9,
    
    # Context
    field_type="motivation",
    company_id="google",
    ats_type="greenhouse",
    
    # Effectiveness
    times_used=5,
    led_to_callback=True,
    last_used=datetime.utcnow()
)
```

---

## 5. ATS Patterns

### Record ATS Pattern

```python
# When discovering a successful pattern
memory.record_ats_pattern(
    ats_type="greenhouse",
    pattern_type="selector",
    pattern_data={
        "field_type": "email",
        "selector": "input[data-qa='email-field']",
        "success_rate": 0.95
    },
    confidence=0.9
)

# Workflow patterns
memory.record_ats_pattern(
    ats_type="workday",
    pattern_type="workflow",
    pattern_data={
        "step": "resume_upload",
        "requires_navigation": True,
        "wait_for_hydration": True
    },
    confidence=0.85
)
```

### Get ATS Patterns

```python
patterns = memory.get_ats_patterns(
    ats_type="greenhouse",
    pattern_type="selector"  # Optional filter
)

for pattern in patterns:
    print(f"Pattern: {pattern.pattern_type}")
    print(f"Data: {pattern.pattern_data}")
    print(f"Success: {pattern.success_count}/{pattern.success_count + pattern.failure_count}")
    print(f"Confidence: {pattern.confidence:.2%}")
```

---

## 6. Optimization Intelligence

Analyzes memory to provide actionable recommendations.

### Get Recommendations

```python
from jobcli.memory import OptimizationIntelligence

intelligence = OptimizationIntelligence(memory)

# Get all recommendations
recommendations = intelligence.get_recommendations()

for rec in recommendations:
    print(f"\n{'='*60}")
    print(f"[{rec.priority.upper()}] {rec.title}")
    print(f"Confidence: {rec.confidence:.0%}")
    print(f"\n{rec.description}")
    
    print(f"\nEvidence:")
    for evidence in rec.evidence:
        print(f"  - {evidence}")
    
    print(f"\nAction Items:")
    for action in rec.action_items:
        print(f"  • {action}")
```

### Example Recommendations

**1. Resume Effectiveness:**
```
[HIGH] Use High-Performing Resume Variant
Confidence: 80%

Resume 'Backend Focused' has 60% callback rate vs. 'General' at 20%

Evidence:
  - Backend Focused: 6/10 callbacks
  - General: 2/10 callbacks

Action Items:
  • Use 'Backend Focused' for similar roles
  • Review what makes 'Backend Focused' more effective
```

**2. Rejection Trends:**
```
[HIGH] Address Primary Rejection Reason: qualifications
Confidence: 75%

Most rejections (8/12) due to qualifications

Evidence:
  - qualifications: 8 rejections
  - experience: 3 rejections
  - location: 1 rejection

Action Items:
  • Target roles that match your qualifications more closely
```

**3. Company Targeting:**
```
[MEDIUM] Focus on High-Success Companies
Confidence: 70%

Found 3 companies with >50% callback rate

Evidence:
  - Stripe: 67% callback rate
  - Airbnb: 60% callback rate
  - Asana: 50% callback rate

Action Items:
  • Apply to more roles at these companies
  • Research what makes these companies a good fit
```

---

### Score Opportunity

Rate how promising an application opportunity is:

```python
score = intelligence.score_opportunity(
    company_name="Google",
    position_title="Software Engineer",
    ats_type="greenhouse"
)

print(f"Opportunity Score: {score.score:.2%}")
print(f"\nReasoning:")
for reason in score.reasoning:
    print(f"  - {reason}")

if score.historical_success_rate:
    print(f"\nHistorical success: {score.historical_success_rate:.0%}")
print(f"Response speed: {score.response_speed}")
```

**Score Calculation:**
- Historical success rate with company: 0-30 points
- Resume match: 0-20 points
- Overall callback rate: 0-20 points
- ATS familiarity: 0-10 points
- Response speed: 0-10 points
- **Total: 0-100 points**

### Suggest Answer

Get suggested answer based on past successful answers:

```python
suggestion = intelligence.suggest_answer(
    question_text="Why do you want to work here?",
    company_name="Google",
    ats_type="greenhouse"
)

if suggestion:
    print(f"Suggested answer:\n{suggestion}")
else:
    print("No similar answers found")
```

### Get Rejection Insights

```python
insights = intelligence.get_rejection_insights()

print("Rejection Insights:")
for insight in insights["insights"]:
    print(f"  • {insight}")

# Trends data
trends = insights["trends"]
print(f"\nTotal rejections: {trends['total_rejections']}")
print(f"Top reason: {trends['top_reason']}")
```

---

## 7. Analytics & Reporting

### Overall Callback Rate

```python
rate = memory.get_callback_rate()
print(f"Overall callback rate: {rate:.2%}")
```

### Rejection Trends

```python
trends = memory.get_rejection_trends()

print(f"Total rejections: {trends['total_rejections']}")
print(f"\nBy reason:")
for reason, count in trends['by_reason'].items():
    print(f"  {reason}: {count}")
print(f"\nTop reason: {trends['top_reason']}")
```

### Resume Effectiveness

```python
for variant in memory.resume_variants.values():
    if variant.applications_count > 0:
        print(f"\n{variant.variant_name}:")
        print(f"  Applications: {variant.applications_count}")
        print(f"  Callbacks: {variant.callbacks_count}")
        print(f"  Callback rate: {variant.callback_rate:.2%}")
        print(f"  Interviews: {variant.interviews_count}")
        print(f"  Offers: {variant.offers_count}")
```

---

## Complete Workflow Example

```python
from jobcli.memory import ApplicationMemory, OptimizationIntelligence
from datetime import datetime, timedelta

# Initialize
memory = ApplicationMemory()
intelligence = OptimizationIntelligence(memory)

# 1. Score opportunity before applying
score = intelligence.score_opportunity(
    "Google",
    "Software Engineer",
    "greenhouse"
)

print(f"Opportunity score: {score.score:.2%}")

if score.score < 0.3:
    print("Low score - consider other opportunities")
else:
    print("Good opportunity - proceed with application")

# 2. Create application
app = memory.create_application(
    company_name="Google",
    position_title="Software Engineer",
    job_url="https://careers.google.com/job123",
    ats_type="greenhouse"
)

# 3. Get best resume
best_resume = memory.get_best_resume_for_role("Software Engineer")
if best_resume:
    memory.update_application(
        app.application_id,
        resume_variant_id=best_resume.variant_id
    )

# 4. Answer questions with suggestions
questions = [
    "Why do you want to work here?",
    "What is your greatest strength?",
    "Tell me about a challenging project"
]

for question in questions:
    # Try to get suggested answer
    suggestion = intelligence.suggest_answer(
        question,
        company_name="Google",
        ats_type="greenhouse"
    )
    
    if suggestion:
        print(f"Using suggested answer for: {question}")
        answer = suggestion
    else:
        # Get answer from user
        answer = input(f"{question}\n> ")
    
    # Save answer
    memory.add_answer(
        app.application_id,
        question,
        answer,
        confidence=0.9 if suggestion else 0.7
    )

# 5. Submit application
memory.update_application(
    app.application_id,
    status="submitted"
)

# 6. Track interactions
# ... recruiter emails ...
memory.add_interaction(
    app.application_id,
    "email",
    recruiter_name="Jane Smith",
    recruiter_email="jane@google.com",
    sentiment="positive"
)

# 7. Update outcome
# If callback:
memory.update_application(
    app.application_id,
    callback_received=True,
    callback_date=datetime.utcnow() + timedelta(days=7),
    status="screening"
)

# Update resume effectiveness
memory.update_resume_effectiveness(
    best_resume.variant_id,
    callback=True
)

# 8. Get insights
recommendations = intelligence.get_recommendations()
print(f"\nGot {len(recommendations)} recommendations")

for rec in recommendations[:3]:  # Top 3
    print(f"\n[{rec.priority.upper()}] {rec.title}")
    print(f"  {rec.description}")
```

---

## Data Persistence

### Storage Structure

```
application_memory/
  applications.json       # All application records
  companies.json          # Company histories
  resume_variants.json    # Resume variants and effectiveness
  questions.json          # Question/answer index
  ats_patterns.json       # ATS-specific patterns
```

### Backup & Export

```python
import shutil
from pathlib import Path

# Backup
backup_dir = Path("application_memory_backup_20260519")
shutil.copytree(memory.memory_dir, backup_dir)

# Load from backup
memory = ApplicationMemory(memory_dir=backup_dir)
```

---

## Best Practices

### 1. Record Everything

Track all applications, even rejections:
```python
# Even if rejected, record it
memory.update_application(
    app_id,
    rejection_received=True,
    rejection_reason="qualifications",
    rejection_details="Looking for 5+ years experience"
)
```

### 2. Update Resume Effectiveness

Always link applications to resume variants:
```python
app = memory.create_application(...)
memory.update_application(
    app.application_id,
    resume_variant_id=resume.variant_id
)

# Update on outcome
memory.update_resume_effectiveness(
    resume.variant_id,
    callback=True,
    interview=True,
    offer=False
)
```

### 3. Save Successful Answers

Mark answers that led to callbacks:
```python
# When callback received
for answer in app.answers:
    qa = memory.questions.get(answer.question_id)
    if qa:
        qa.led_to_callback = True

memory._save_questions()
```

### 4. Regular Intelligence Reviews

Review recommendations periodically:
```python
# Weekly review
recommendations = intelligence.get_recommendations()

print(f"\n=== Weekly Application Intelligence ===")
print(f"Overall callback rate: {memory.get_callback_rate():.2%}")

print(f"\nTop recommendations:")
for rec in recommendations[:5]:
    print(f"  [{rec.priority}] {rec.title}")
```

### 5. Track Recruiter Interactions

Build recruiter relationships:
```python
company = memory.get_company_insights("google")
if company and company.known_recruiters:
    print("Known contacts at Google:")
    for recruiter in company.known_recruiters:
        print(f"  - {recruiter['name']} ({recruiter['email']})")
```

---

## Integration with Application Flow

```python
from jobcli.memory import ApplicationMemory, OptimizationIntelligence
from jobcli.execution import ExecutionEngine

# Initialize
memory = ApplicationMemory()
intelligence = OptimizationIntelligence(memory)

# Before applying
score = intelligence.score_opportunity(company_name, position, ats_type)

if score.score > 0.4:
    # Good opportunity, proceed
    app = memory.create_application(company_name, position, url, ats_type)
    
    # Use best resume
    resume = memory.get_best_resume_for_role(position)
    if resume:
        memory.update_application(app.application_id, resume_variant_id=resume.variant_id)
    
    # Execute application with engine
    engine = ExecutionEngine(page, ats_type)
    
    # For each question, try to use saved answer
    for question_text in questions:
        answer = intelligence.suggest_answer(question_text, company_name, ats_type)
        
        if answer:
            # Use suggested answer
            result = engine.execute(FillInputAction(..., value=answer))
        else:
            # Get new answer from user
            answer = get_user_input(question_text)
            result = engine.execute(FillInputAction(..., value=answer))
        
        # Save answer
        memory.add_answer(app.application_id, question_text, answer, confidence=0.9 if answer else 0.7)
    
    # Update status
    memory.update_application(app.application_id, status="submitted")
```

---

**The application memory system learns from every application, continuously improving recommendations and success rates over time.**
