import requests

from app.database import save_jobs

# tool   himalayas
def get_himalayas_job(query: str) -> list[dict]:
    """Search real remote jobs from Himalayas."""

    url = "https://himalayas.app/jobs/api/search"
    params = {
        "q": query,
        "worldwide": "true",
        "seniority": "Senior",
        "sort": "recent",
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()
    jobs = data.get("jobs", [])
    save_jobs(jobs)
    results = []
    for job in jobs[:10]:
        results.append(
            {
                "title": job.get("title"),
                "company": job.get("companyName"),
                "employment_type": job.get("employmentType"),
                "location_restrictions": job.get("locationRestrictions"),
                "timezone_restrictions": job.get("timezoneRestriction"),
                "published_at": job.get("pubDate"),
                "salary_min": job.get("minSalary"),
                "salary_max": job.get("maxSalary"),
                "currency": job.get("currency"),
                "apply_url": job.get("applicationLink"),
                "description": job.get("excerpt"),
            }
        )
    return results
