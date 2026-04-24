#!/usr/bin/env python
"""
Quick Setup Script for Claude Agent with JobCLI

This script helps you configure and test Claude agent integration.
Run this to verify everything is working correctly.
"""

import os
import sys
import json
from pathlib import Path


def check_claude_api_key():
    """Check if Claude API key is configured."""
    api_key = os.getenv("CLAUDE_API_KEY")
    
    if not api_key:
        print("❌ CLAUDE_API_KEY not set in environment")
        print("\n   To set it:")
        print("   Linux/Mac:   export CLAUDE_API_KEY='your-key-here'")
        print("   Windows:     set CLAUDE_API_KEY=your-key-here")
        print("   PowerShell:  $env:CLAUDE_API_KEY = 'your-key-here'")
        return False
    
    print("✅ CLAUDE_API_KEY found")
    print(f"   Key preview: {api_key[:10]}...{api_key[-5:]}")
    return True


def verify_claude_module_installed():
    """Verify Claude agent module is available."""
    try:
        from jobcli.core.claude_agent import ClaudeAgentStrategy
        print("✅ Claude agent module installed")
        return True
    except ImportError as e:
        print(f"❌ Claude agent module not found: {e}")
        return False


def verify_llm_client_updated():
    """Verify LLMClient supports Claude."""
    try:
        from jobcli.llm.client import LLMClient
        
        # Check if 'claude' is in the type hints
        import inspect
        sig = inspect.signature(LLMClient.__init__)
        provider_param = sig.parameters.get('provider')
        
        if provider_param:
            print("✅ LLMClient supports Claude provider")
            return True
        else:
            print("❌ LLMClient provider parameter not found")
            return False
    except Exception as e:
        print(f"❌ Error checking LLMClient: {e}")
        return False


def verify_schema_updated():
    """Verify schemas support Claude."""
    try:
        from jobcli.core.schemas import Config
        
        # Try to create a config with Claude
        config = Config(
            default_llm_provider="claude",
            claude_api_key="test-key"
        )
        print("✅ Config schema supports Claude")
        return True
    except Exception as e:
        print(f"❌ Schema error: {e}")
        return False


def test_claude_client():
    """Test creating a Claude LLM client."""
    try:
        from jobcli.llm.client import LLMClient
        
        api_key = os.getenv("CLAUDE_API_KEY", "test-key")
        client = LLMClient(provider="claude", api_key=api_key)
        
        print("✅ Claude LLMClient created successfully")
        print(f"   Model: {client.model}")
        print(f"   Provider: {client.provider}")
        return True
    except Exception as e:
        print(f"❌ Error creating Claude client: {e}")
        return False


def test_claude_agent():
    """Test creating a Claude agent."""
    try:
        from jobcli.core.claude_agent import ClaudeAgentStrategy
        
        api_key = os.getenv("CLAUDE_API_KEY", "test-key")
        agent = ClaudeAgentStrategy(api_key=api_key)
        
        print("✅ Claude agent created successfully")
        print(f"   Model: {agent.model}")
        print(f"   Available tools: {len(agent.tools)}")
        for tool in agent.tools:
            print(f"     - {tool['name']}")
        return True
    except Exception as e:
        print(f"❌ Error creating Claude agent: {e}")
        return False


def suggest_next_steps():
    """Print suggested next steps."""
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    
    print("""
1. Set your Claude API key:
   export CLAUDE_API_KEY='your-api-key-from-claude-ai'

2. Update your JobCLI config:
   default_llm_provider: claude
   claude_api_key: ${CLAUDE_API_KEY}

3. Run a test application:
   python -m jobcli --job-url <job-url>

4. Monitor execution:
   tail -f logs/jobcli.jsonl

5. For advanced usage, see:
   - CLAUDE_AGENT_GUIDE.md
   - claude_examples.py
   - CLAUDE_IMPLEMENTATION_SUMMARY.md

""")


def main():
    """Run all checks."""
    print("=" * 60)
    print("CLAUDE AGENT SETUP VERIFICATION")
    print("=" * 60)
    print()
    
    checks = [
        ("Claude API Key", check_claude_api_key),
        ("Claude Module", verify_claude_module_installed),
        ("LLMClient Support", verify_llm_client_updated),
        ("Schema Support", verify_schema_updated),
        ("Claude Client", test_claude_client),
        ("Claude Agent", test_claude_agent),
    ]
    
    results = []
    for check_name, check_func in checks:
        print(f"\nChecking {check_name}...")
        result = check_func()
        results.append((check_name, result))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {check_name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All checks passed! Claude agent is ready to use.")
        suggest_next_steps()
        return 0
    else:
        print("\n⚠️  Some checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
