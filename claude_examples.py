"""
Example: Using Claude Agent with JobCLI Engine

This file shows practical examples of integrating Claude with the existing engine.
"""

import json
import os
from pathlib import Path
from typing import Optional

from jobcli.core.claude_agent import ClaudeAgentStrategy
from jobcli.core.engine import ApplicationEngine
from jobcli.core.logger import JobLogger
from jobcli.core.schemas import Config, ResumeData
from jobcli.llm.client import LLMClient
from jobcli.llm.ax_tree_extractor import AccessibilityTree
from jobcli.storage.models import Database


def _get_claude_api_key() -> Optional[str]:
    return os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")


def example_1_basic_claude_client():
    """Example 1: Using Claude as an LLM provider with existing LLMClient."""
    
    print("Example 1: Basic Claude LLM Client")
    print("=" * 50)
    
    # Initialize Claude as the LLM provider
    claude_api_key = _get_claude_api_key()
    if not claude_api_key:
        print("âœ— Missing CLAUDE_API_KEY (or ANTHROPIC_API_KEY). Set it in your environment to run this example.")
        return
    llm_client = LLMClient(
        provider="claude",  # New provider option!
        api_key=claude_api_key
    )
    
    # Use it just like any other LLM provider
    # It will use Claude's latest model automatically
    print(f"✓ Claude client initialized")
    print(f"  Model: {llm_client.model}")
    print(f"  Provider: {llm_client.provider}")
    

def example_2_claude_agent_strategy():
    """Example 2: Using advanced Claude Agent Strategy."""
    
    print("\nExample 2: Advanced Claude Agent Strategy")
    print("=" * 50)
    
    # Initialize logger for tracking
    logger = JobLogger("claude_example.jsonl")
    
    # Initialize the advanced Claude agent
    claude_api_key = _get_claude_api_key()
    if not claude_api_key:
        print("âœ— Missing CLAUDE_API_KEY (or ANTHROPIC_API_KEY). Set it in your environment to run this example.")
        return
    claude_agent = ClaudeAgentStrategy(
        api_key=claude_api_key,
        logger=logger
    )
    
    print(f"✓ Claude agent initialized with {len(claude_agent.tools)} tools")
    for tool in claude_agent.tools:
        print(f"  - {tool['name']}: {tool['description'][:50]}...")


def example_3_integration_with_engine():
    """Example 3: Integrating Claude with the existing ApplicationEngine."""
    
    print("\nExample 3: Integration with ApplicationEngine")
    print("=" * 50)
    
    # Load configuration
    claude_api_key = _get_claude_api_key()
    if not claude_api_key:
        print("âœ— Missing CLAUDE_API_KEY (or ANTHROPIC_API_KEY). Set it in your environment to run this example.")
        return
    config = Config(
        default_llm_provider="claude",  # Use Claude by default
        claude_api_key=claude_api_key,
        headless=True
    )
    
    # Load resume
    resume_path = Path("example_resume.json")
    if resume_path.exists():
        with open(resume_path) as f:
            resume_data = ResumeData(**json.load(f))
        print(f"✓ Loaded resume for {resume_data.personal.first_name} {resume_data.personal.last_name}")
    else:
        print("✗ Resume file not found - skipping engine example")
        return
    
    # The engine will automatically use Claude if configured
    # Simply create your engine as usual:
    # engine = ApplicationEngine(config, resume_data, database)
    # engine.apply_to_job(job)
    # 
    # And Claude will handle all LLM analysis!
    
    print("✓ Engine will use Claude for all LLM tasks")
    print("  Configuration:")
    print(f"    - Provider: {config.default_llm_provider}")
    print(f"    - API Key: {'*' * 10 + config.claude_api_key[-4:] if config.claude_api_key else 'Not set'}")


def example_4_claude_with_memory_context():
    """Example 4: Using Claude with memory context for consistency."""
    
    print("\nExample 4: Claude with Memory Context")
    print("=" * 50)
    
    # Memory context from previous applications
    memory_context = """
    Known Answers:
    - Visa Sponsorship: "No, I do not need sponsorship" (based on US citizenship)
    - Preferred Work Location: "San Francisco, CA" (home location)
    - Work Authorization: "Yes, I am authorized to work in the US"
    - Gender: "Male" (from demographics)
    - Pronouns: "he/him" (inferred from gender)
    
    Previous Application Patterns:
    - Always fills all fields completely
    - Uses LinkedIn URL: https://www.linkedin.com/in/[user]/
    - Provides resume PDF: /path/to/resume.pdf
    - Answers EEOC questions when required
    """
    
    logger = JobLogger("claude_memory_example.jsonl")
    claude_api_key = _get_claude_api_key()
    if not claude_api_key:
        print("âœ— Missing CLAUDE_API_KEY (or ANTHROPIC_API_KEY). Set it in your environment to run this example.")
        return
    agent = ClaudeAgentStrategy(
        api_key=claude_api_key,
        logger=logger
    )
    
    print("✓ Claude agent initialized with memory support")
    print("✓ Agent will use memory context for consistent answers")
    print("Memory context:")
    for line in memory_context.strip().split("\n"):
        print(f"  {line}")


def example_5_error_handling():
    """Example 5: Error handling and retry logic."""
    
    print("\nExample 5: Error Handling & Retry Logic")
    print("=" * 50)
    
    logger = JobLogger("claude_errors.jsonl", level="INFO")
    
    # The client includes automatic retry logic
    claude_api_key = _get_claude_api_key()
    if not claude_api_key:
        print("âœ— Missing CLAUDE_API_KEY (or ANTHROPIC_API_KEY). Set it in your environment to run this example.")
        return
    llm_client = LLMClient(
        provider="claude",
        api_key=claude_api_key,
        logger=logger
    )
    
    print("✓ Claude client includes automatic retry logic:")
    print("  - 3 retry attempts with exponential backoff")
    print("  - Validates responses before returning")
    print("  - Logs all errors for debugging")
    print("  - Graceful fallback on failure")


def example_6_configuration_file():
    """Example 6: Using Claude via configuration file."""
    
    print("\nExample 6: Configuration File Setup")
    print("=" * 50)
    
    config_example = """
# config.yml
default_llm_provider: claude
claude_api_key: ${CLAUDE_API_KEY}  # Set via environment variable

interaction_mode: supervised  # Pause for confirmation
headless: true
max_retries: 3

# Other settings...
resume_pdf_path: ./resume.pdf
log_directory: ./logs
"""
    
    print("Example configuration file:")
    print(config_example)
    
    print("\nAlternatively, set environment variable:")
    print("  export CLAUDE_API_KEY='your-api-key-here'")
    print("  export DEFAULT_LLM_PROVIDER='claude'")


def example_7_monitoring_and_debugging():
    """Example 7: Monitoring Claude agent execution."""
    
    print("\nExample 7: Monitoring & Debugging")
    print("=" * 50)
    
    # Enable detailed logging
    logger = JobLogger(
        "claude_debug.jsonl",
        level="DEBUG"  # Verbose logging
    )
    
    claude_api_key = _get_claude_api_key()
    if not claude_api_key:
        print("âœ— Missing CLAUDE_API_KEY (or ANTHROPIC_API_KEY). Set it in your environment to run this example.")
        return
    agent = ClaudeAgentStrategy(
        api_key=claude_api_key,
        logger=logger
    )
    
    print("✓ Debug logging enabled")
    print("✓ All Claude API calls will be logged to claude_debug.jsonl")
    print("✓ Tool executions and reasoning will be captured")
    print("✓ Use this for debugging form-filling issues")


# Run all examples
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CLAUDE AGENT FOR JOBCLI - EXAMPLES")
    print("=" * 60)
    
    try:
        example_1_basic_claude_client()
        example_2_claude_agent_strategy()
        example_3_integration_with_engine()
        example_4_claude_with_memory_context()
        example_5_error_handling()
        example_6_configuration_file()
        example_7_monitoring_and_debugging()
        
        print("\n" + "=" * 60)
        print("QUICK START CHECKLIST:")
        print("=" * 60)
        print("☐ 1. Set CLAUDE_API_KEY environment variable")
        print("☐ 2. Update config to use: default_llm_provider: claude")
        print("☐ 3. Run your job applications as usual")
        print("☐ 4. Claude will handle all LLM analysis!")
        print("☐ 5. Check logs for detailed execution info")
        print("\n✓ All examples completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error in examples: {e}")
        import traceback
        traceback.print_exc()
