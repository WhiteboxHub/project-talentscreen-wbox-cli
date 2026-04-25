import re

def _is_matching_option(opts, target_val):
    target_val = target_val.lower().strip()
    if not target_val: return False
    for opt in opts:
        val = opt.lower().strip()
        if target_val in val or val in target_val:
            return True
    return False

opts = ["United States", "Canada"]
print(_is_matching_option(opts, "United States of America"))
print(_is_matching_option(opts, "United Kingdom"))
