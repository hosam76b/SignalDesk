import sys
from config import settings
from app.services.apify_service import ApifyService
from app.services.scraper_service import ScraperService

# Step 2:
apify_service = ApifyService()
has_token = bool(settings.apify_api_token)
has_actor = bool(settings.apify_actor_id)
is_configured = apify_service.is_configured

print("Step 2 results:")
print(f"apify_api_token_exists: {has_token}")
print(f"actor_id_exists: {has_actor}")
print(f"is_configured: {is_configured}")

# Step 3:
print("\nStep 3 results:")
test_data = {
    "raw_text": "This is a test post raw text content.",
    "source": "https://facebook.com/testpage",
    "created_at": "2026-08-23T12:00:00Z"
}
try:
    normalized = ScraperService.normalize_post(test_data, "facebook", "https://facebook.com/testpage")
    print("Normalized post dictionary:")
    import pprint
    pprint.pprint(normalized)
    
    # Verify exact keys
    keys_to_check = ["content", "raw_text", "source", "source_url", "published_at", "created_at"]
    all_keys_present = True
    for key in keys_to_check:
        present = key in normalized
        print(f"Key '{key}' present: {present} (Value: {normalized.get(key)})")
        if not present:
            all_keys_present = False
    print(f"Verification success: {all_keys_present}")
except Exception as e:
    print(f"Error during normalize_post test: {e}")
    sys.exit(1)
