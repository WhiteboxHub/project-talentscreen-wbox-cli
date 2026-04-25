import os
import re

ats_dir = "/Users/bavishsaireddy/Desktop/wbox-cli/jobcli/locators/ats"

# Generic ATS script replacement
for f in os.listdir(ats_dir):
    if f.endswith("_handler.py") and f not in ("base_handler.py", "lever_handler.py", "workday_handler.py"):
        fp = os.path.join(ats_dir, f)
        with open(fp, "r") as file:
            c = file.read()
        
        c = re.sub(
            r'self\.page\.fill\(([^,]+),\s*([^,)]+)(?:,\s*timeout=\d+)?\)',
            r'self.humanized_fill(self.page.locator(\1).first, \2)',
            c
        )
        with open(fp, "w") as file:
            file.write(c)

# Form fields replacement
ff_path = "/Users/bavishsaireddy/Desktop/wbox-cli/jobcli/locators/form_fields.py"
with open(ff_path, "r") as file:
    ff_content = file.read()

ff_content = "from jobcli.core.human_interaction import humanized_fill\n" + ff_content
ff_content = re.sub(
    r'self\.page\.fill\(([^,]+),\s*([^,)]+)(?:,\s*timeout=\d+)?\)',
    r'humanized_fill(self.page, self.page.locator(\1).first, \2)',
    ff_content
)

with open(ff_path, "w") as file:
    file.write(ff_content)

print("Patch applied to ATS handlers (excluding workday) and form_fields.py")
