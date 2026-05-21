import os
import json
from playwright.sync_api import sync_playwright
from jobcli.profile.schemas import PersonalInfo, ResumeData
from jobcli.extension.autofill_bridge import inject_resume_to_extension_storage
from jobcli.utils.extension_helpers import resolve_extension_dir

def main():
    # 1. Create a dummy resume
    print("📝 Creating dummy resume data...")
    dummy_resume = ResumeData(
        personal=PersonalInfo(
            first_name="LiveTest",
            last_name="User",
            email="livetest@example.com",
            phone="555-123-4567"
        )
    )

    # 2. Resolve extension dir
    ext_dir = resolve_extension_dir()
    if not ext_dir:
        print("❌ Could not find extension directory")
        return
    
    print(f"✅ Found extension at: {ext_dir}")

    # 3. Launch browser
    with sync_playwright() as p:
        args = chromium_extension_launch_args(ext_dir)
        # Use a fresh temporary profile so we don't pick up old state
        import tempfile
        user_data_dir = tempfile.mkdtemp(prefix="jobcli_test_profile_")
        
        print(f"🚀 Launching browser with extension (profile: {user_data_dir})...")
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=args,
        )

        # 4. Inject resume
        print("\n💉 Injecting resume data...")
        class DummyLogger:
            def info(self, msg): print(f"  [INFO] {msg}")
            def warning(self, msg): print(f"  [WARN] {msg}")
            def debug(self, msg): print(f"  [DEBUG] {msg}")
            
        success = inject_resume_to_extension_storage(
            context,
            dummy_resume,
            logger=DummyLogger()
        )
        
        if success:
            print("✅ Injection function returned True")
            
            # Let's verify what's actually in chrome.storage.local!
            ext_id = None
            for sw in context.service_workers:
                url = sw.url or ""
                if url.startswith("chrome-extension://"):
                    ext_id = url.split("/")[2]
                    break
            
            if ext_id:
                print(f"\n🔍 Verifying chrome.storage.local for ext_id: {ext_id}...")
                # We can query the storage using the service worker
                for sw in context.service_workers:
                    if ext_id in (sw.url or ""):
                        stored_data = sw.evaluate('''() => {
                            return new Promise((resolve) => {
                                chrome.storage.local.get(null, (items) => {
                                    resolve(items);
                                });
                            });
                        }''')
                        
                        print("\n📦 STORAGE KEYS FOUND:")
                        print(list(stored_data.keys()))
                        
                        if "resumeData" in stored_data:
                            email = stored_data["resumeData"].get("basics", {}).get("email")
                            print(f"✅ resumeData is present! Extracted email: {email}")
                            
                            print("\n📄 Full resumeData JSON:")
                            print(json.dumps(stored_data["resumeData"], indent=2))
                        else:
                            print("❌ resumeData NOT found in storage!")
                            
                        if "normalizedData" in stored_data:
                            print(f"✅ normalizedData is present!")
                        break
        else:
            print("❌ Injection function returned False")

        print("\n🛑 Closing browser...")
        context.close()

if __name__ == "__main__":
    main()
