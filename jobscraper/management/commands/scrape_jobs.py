"""
Advanced Hybrid Job Scraper for Bangladesh job sites
Usage:
    python manage.py scrape_jobs
    python manage.py scrape_jobs --source "BDJobs"
"""

import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from jobscraper.models import JobSource, Job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape jobs from supported job websites using requests + Playwright"

    def add_arguments(self, parser):
        parser.add_argument("--source", type=str, help="Scrape a specific source by name")

    # -------------------------------------------------
    # Main
    # -------------------------------------------------

    def handle(self, *args, **options):
        source_name = options.get("source")

        sources = JobSource.objects.filter(is_active=True)
        if source_name:
            sources = sources.filter(name__icontains=source_name)

        if not sources.exists():
            self.stdout.write(self.style.WARNING("No active sources found."))
            return

        total_new = 0
        total_parsed = 0

        for source in sources:
            self.stdout.write(f"\nScraping: {source.name}")
            try:
                jobs = self.route_scraper(source)
                parsed_count = len(jobs)

                new_count = 0
                for job in jobs[:200]:
                    if self.save_job(job, source):
                        new_count += 1

                total_new += new_count
                total_parsed += parsed_count

                if new_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(f"  -> {new_count} new jobs saved ({parsed_count} parsed)")
                    )
                elif parsed_count > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  -> 0 new jobs saved ({parsed_count} parsed, likely duplicates)"
                        )
                    )
                else:
                    self.stdout.write(self.style.WARNING("  -> No jobs found"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  -> Error: {str(e)}"))
                logger.exception("Scraping failed for source %s", source.name)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Total new jobs saved: {total_new} | Total parsed: {total_parsed}"
            )
        )

    # -------------------------------------------------
    # Router
    # -------------------------------------------------

    def route_scraper(self, source):
        base_url = (source.base_url or "").lower()
        name = (source.name or "").lower()

        if "remoteok" in base_url or "remote ok" in name:
            return self.scrape_remote_ok_api()

        if "bdjobs" in base_url or "bdjobs" in name:
            return self.scrape_bdjobs_api()

        if "prothomalo" in base_url or "prothom alo" in name:
            return self.scrape_prothom_alo(source.base_url)

        if "careerjet" in base_url or "careerjet" in name:
            return self.scrape_careerjet(source.base_url)

        if "shomvob" in base_url or "shomvob" in name:
            return self.scrape_shomvob_playwright(source.base_url)

        if "skill.jobs" in base_url or "skill jobs" in name:
            return self.scrape_skill_jobs(source.base_url)

        if "jagojobs" in base_url or "jago jobs" in name:
            return self.scrape_jago_jobs(source.base_url)

        if "myjobs" in base_url or "myjobs" in name:
            return self.scrape_myjobs_bd(source.base_url)

        if "alljobs" in base_url or "teletalk" in base_url or "teletalk" in name:
            return self.scrape_teletalk(source.base_url)

        if "niyog" in base_url or "niyog" in name:
            return self.scrape_niyog_playwright(source.base_url)

        return self.scrape_universal(source.base_url, source.name)

    # -------------------------------------------------
    # HTTP helpers
    # -------------------------------------------------

    def get_page(self, url, timeout=30):
        session = requests.Session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.google.com/",
        }
        resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()

        self.stdout.write(
            f"    Status: {resp.status_code} | Final URL: {resp.url} | Bytes: {len(resp.text)}"
        )
        return resp

    def get_rendered_html(self, url, wait_ms=7000):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 2200},
                locale="en-US",
            )
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            final_url = page.url
            browser.close()

        self.stdout.write(
            f"    Rendered with Playwright | Final URL: {final_url} | Bytes: {len(html)}"
        )
        return html

    # -------------------------------------------------
    # Text helpers
    # -------------------------------------------------

    def clean_text(self, value):
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()

    def is_valid_job(self, title, href):
        title = self.clean_text(title)
        href = (href or "").strip()

        if not title or len(title) < 4:
            return False
        if not href:
            return False
        if href.startswith("#") or href.lower().startswith("javascript:"):
            return False

        bad_exact = {
            "jobs",
            "job",
            "home",
            "menu",
            "apply",
            "read more",
            "details",
            "login",
            "register",
            "sign in",
            "search",
            "next",
            "previous",
            "quick links",
            "job search",
            "create account",
            "employer list",
            "my bdjobs panel",
            "view desktop version",
            "বাংলায় দেখুন",
            "pagination jobs",
            "back",
            "top",
            "see more",
        }
        if title.lower() in bad_exact:
            return False

        bad_contains = [
            "privacy",
            "cookie",
            "terms",
            "subscribe",
            "advertise",
            "sponsored",
            "panel",
            "desktop version",
            "quick links",
            "pagination",
        ]
        low = title.lower()
        if any(x in low for x in bad_contains):
            return False

        return True

    def build_job(
        self,
        title,
        company,
        location,
        apply_url,
        work_mode="onsite",
        job_type="full_time",
        deadline=None,
        description="",
    ):
        return {
            "title": self.clean_text(title)[:200],
            "company": self.clean_text(company)[:200] or "Unknown Company",
            "location": self.clean_text(location)[:200] or "Bangladesh",
            "work_mode": work_mode,
            "job_type": job_type,
            "apply_url": apply_url.strip(),
            "deadline": deadline or (date.today() + timedelta(days=30)),
            "description": self.clean_text(description)[:2000],
        }

    def parse_date_from_text(self, text):
        if not text:
            return date.today() + timedelta(days=30)

        text = self.clean_text(text)
        patterns = [
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.I)
            if m:
                raw = m.group(0)
                for fmt in ("%B %d, %Y", "%d %B %Y", "%b %d, %Y"):
                    try:
                        return datetime.strptime(raw, fmt).date()
                    except Exception:
                        pass
        return date.today() + timedelta(days=30)

    def infer_work_mode(self, text):
        low = (text or "").lower()
        if "remote" in low or "work from home" in low:
            return "remote"
        if "hybrid" in low:
            return "hybrid"
        return "onsite"

    # -------------------------------------------------
    # Site scrapers
    # -------------------------------------------------

    def scrape_remote_ok_api(self):
        jobs = []
        seen = set()
        try:
            resp = requests.get(
                "https://remoteok.com/api",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data[1:100]:
                title = item.get("position", "")
                company = item.get("company", "")
                apply_url = item.get("url", "")
                location = item.get("location", "Remote")

                if not self.is_valid_job(title, apply_url):
                    continue
                if apply_url in seen:
                    continue
                seen.add(apply_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company=company or "Remote OK",
                        location=location or "Remote",
                        apply_url=apply_url,
                        work_mode="remote",
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Remote OK API failed: {str(e)}"))
        return jobs

    def scrape_bdjobs_api(self):
        jobs = []
        seen = set()

        try:
            page = 1
            max_pages = 5

            while page <= max_pages:
                api_url = (
                    "https://api.bdjobs.com/Jobs/api/JobSearch/GetJobSearch"
                    "?Icat=&industry=&category=&org=&jobNature=&Fcat=&location=&Qot="
                    "&jobType=&jobLevel=&postedWithin=&deadline=&keyword=&pg={page}"
                    "&qAge=&Salary=&experience=&gender=&MExp=&genderB=&MPostings="
                    "&MCat=&version=&rpp=100&Newspaper=&armyp=&QDisablePerson=&pwd="
                    "&workplace=&facilitiesForPWD=&SaveFilterList=&UserFilterName="
                    "&HUserFilterName=&earlyJobAccess=&isPro=0&ToggleJobs=true&isFresher=false"
                ).format(page=page)

                resp = requests.get(
                    api_url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json, text/plain, */*",
                        "Referer": "https://bdjobs.com/",
                        "Origin": "https://bdjobs.com",
                    },
                    timeout=30,
                )
                resp.raise_for_status()

                data = resp.json()
                items = data.get("data", []) if isinstance(data, dict) else []

                self.stdout.write(f"    BDJobs API page {page}: {len(items)} items")

                if not items:
                    break

                for item in items:
                    job_id = str(item.get("Jobid", "")).strip()
                    title = self.clean_text(item.get("jobTitle", ""))
                    company = self.clean_text(item.get("companyName", "BDJobs"))
                    location = self.clean_text(item.get("location", "Bangladesh"))
                    description = self.clean_text(item.get("jobContext", ""))
                    online_job = item.get("OnlineJob", False)

                    if not job_id or not title:
                        continue

                    apply_url = f"https://bdjobs.com/jobdetails.asp?id={job_id}"

                    if apply_url in seen:
                        continue
                    seen.add(apply_url)

                    deadline = date.today() + timedelta(days=30)
                    deadline_db = item.get("deadlineDB")
                    deadline_text = item.get("deadline")

                    if deadline_db:
                        try:
                            deadline = datetime.strptime(deadline_db, "%Y-%m-%dT%H:%M:%SZ").date()
                        except Exception:
                            pass
                    elif deadline_text:
                        try:
                            deadline = datetime.strptime(deadline_text, "%b %d, %Y").date()
                        except Exception:
                            pass

                    work_mode = "remote" if online_job or "remote" in location.lower() else "onsite"

                    jobs.append(
                        self.build_job(
                            title=title,
                            company=company,
                            location=location or "Bangladesh",
                            apply_url=apply_url,
                            work_mode=work_mode,
                            job_type="full_time",
                            deadline=deadline,
                            description=description,
                        )
                    )

                page += 1

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    BDJobs API failed: {str(e)}"))

        self.stdout.write(f"    Parsed BDJobs API jobs: {len(jobs)}")
        return jobs

    def scrape_prothom_alo(self, url):
        jobs = []
        seen = set()
        try:
            resp = self.get_page(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    Prothom Alo links found: {len(links)}")

            for a in links[:1500]:
                href = a.get("href", "").strip()
                title = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin("https://www.prothomalo.com", href)

                if not self.is_valid_job(title, full_url):
                    continue

                if "/chakri/" not in full_url:
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company="Prothom Alo Jobs",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode="onsite",
                        deadline=self.parse_date_from_text(title),
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Prothom Alo failed: {str(e)}"))
        return jobs

    def scrape_careerjet(self, url):
        jobs = []
        seen = set()
        try:
            search_url = url
            if "search/jobs" not in search_url:
                search_url = "https://www.careerjet.com.bd/search/jobs?s=software"

            resp = self.get_page(search_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            items = soup.select("article, .job, .result")
            self.stdout.write(f"    CareerJet result blocks: {len(items)}")

            for item in items[:150]:
                a = item.select_one("a[href]")
                title_el = item.select_one("h2, h3, a")
                company_el = item.select_one('[class*="company"]')
                location_el = item.select_one('[class*="location"]')

                href = a.get("href", "").strip() if a else ""
                title = self.clean_text(title_el.get_text()) if title_el else ""
                full_url = urljoin(resp.url, href) if href else ""

                if not self.is_valid_job(title, full_url):
                    continue
                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company=self.clean_text(company_el.get_text()) if company_el else "CareerJet BD",
                        location=self.clean_text(location_el.get_text()) if location_el else "Bangladesh",
                        apply_url=full_url,
                        work_mode="onsite",
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    CareerJet failed: {str(e)}"))
        return jobs

    def scrape_shomvob_playwright(self, url):
        jobs = []
        seen = set()
        try:
            html = self.get_rendered_html(url, wait_ms=9000)
            soup = BeautifulSoup(html, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    Shomvob rendered links found: {len(links)}")

            for a in links[:3000]:
                href = a.get("href", "").strip()
                text = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin("https://app.shomvob.co", href)

                if not self.is_valid_job(text, full_url):
                    continue

                full_low = full_url.lower()
                text_low = text.lower()

                blocked_parts = [
                    "login", "register", "sign", "privacy", "terms",
                    "about", "contact", "faq", "blog", "policy",
                    "employer", "candidate", "dashboard", "profile",
                ]
                if any(x in full_low for x in blocked_parts):
                    continue

                likely_job_url = any(
                    x in full_low for x in [
                        "/job", "/jobs", "vacancy", "opening", "career", "position"
                    ]
                )

                likely_job_text = any(
                    x in text_low for x in [
                        "engineer", "developer", "executive", "manager",
                        "officer", "intern", "designer", "specialist",
                        "assistant", "coordinator", "sales", "marketing",
                        "teacher", "technician", "analyst", "accountant", "hr"
                    ]
                )

                if not likely_job_url and not likely_job_text:
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=text,
                        company="Shomvob",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode=self.infer_work_mode(text),
                    )
                )

            self.stdout.write(f"    Parsed Shomvob jobs: {len(jobs)}")

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Shomvob failed: {str(e)}"))
        return jobs

    def scrape_skill_jobs(self, url):
        jobs = []
        seen = set()
        try:
            resp = self.get_page(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    Skill Jobs links found: {len(links)}")

            for a in links[:1500]:
                href = a.get("href", "").strip()
                title = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin(resp.url, href)

                if not self.is_valid_job(title, full_url):
                    continue

                if "/job" not in full_url.lower() and "/jobs" not in full_url.lower():
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company="Skill Jobs",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode=self.infer_work_mode(title),
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Skill Jobs failed: {str(e)}"))
        return jobs

    def scrape_jago_jobs(self, url):
        jobs = []
        seen = set()
        try:
            resp = self.get_page(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    JagoJobs links found: {len(links)}")

            for a in links[:2000]:
                href = a.get("href", "").strip()
                title = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin(resp.url, href)

                if not self.is_valid_job(title, full_url):
                    continue

                if "/job" not in full_url.lower() and "/jobs" not in full_url.lower():
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company="Jago Jobs",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode=self.infer_work_mode(title),
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    JagoJobs failed: {str(e)}"))
        return jobs

    def scrape_myjobs_bd(self, url):
        jobs = []
        seen = set()
        try:
            resp = self.get_page(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            title_links = soup.select("h4 a[href], h3 a[href], h2 a[href], a[href]")
            self.stdout.write(f"    MyJobs candidate links found: {len(title_links)}")

            for a in title_links[:1500]:
                href = a.get("href", "").strip()
                title = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin("https://myjobs.com.bd", href)

                if not self.is_valid_job(title, full_url):
                    continue

                if "/job" not in full_url.lower() and "/posted-jobs" not in full_url.lower():
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company="MyJobs",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode="onsite",
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    MyJobs failed: {str(e)}"))
        return jobs

    def scrape_teletalk(self, url):
        jobs = []
        seen = set()
        try:
            resp = self.get_page(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    Teletalk links found: {len(links)}")

            for a in links[:1500]:
                href = a.get("href", "").strip()
                title = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin("https://alljobs.teletalk.com.bd", href)

                if not self.is_valid_job(title, full_url):
                    continue

                if "job" not in full_url.lower():
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company="Alljobs by Teletalk",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode="onsite",
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Teletalk failed: {str(e)}"))
        return jobs

    def scrape_niyog_playwright(self, url):
        jobs = []
        seen = set()
        try:
            html = self.get_rendered_html(url, wait_ms=7000)
            soup = BeautifulSoup(html, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    Niyog rendered links found: {len(links)}")

            for a in links[:2500]:
                href = a.get("href", "").strip()
                text = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin("https://www.niyog.co", href)

                if not self.is_valid_job(text, full_url):
                    continue

                if "/job" not in full_url.lower() and "/jobs" not in full_url.lower():
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=text,
                        company="Niyog",
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode=self.infer_work_mode(text),
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Niyog failed: {str(e)}"))
        return jobs

    # -------------------------------------------------
    # Universal fallback
    # -------------------------------------------------

    def scrape_universal(self, url, source_name):
        jobs = []
        seen = set()
        try:
            resp = self.get_page(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            links = soup.select("a[href]")
            self.stdout.write(f"    Universal links found: {len(links)}")

            for a in links[:2000]:
                href = a.get("href", "").strip()
                title = self.clean_text(a.get_text(" ", strip=True))
                full_url = urljoin(resp.url, href)

                if not self.is_valid_job(title, full_url):
                    continue

                if not any(
                    x in full_url.lower()
                    for x in ["/job", "/jobs", "career", "vacancy", "position"]
                ):
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                jobs.append(
                    self.build_job(
                        title=title,
                        company=source_name,
                        location="Bangladesh",
                        apply_url=full_url,
                        work_mode=self.infer_work_mode(title),
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Universal failed: {str(e)}"))
        return jobs

    # -------------------------------------------------
    # Save
    # -------------------------------------------------

    def save_job(self, job_data, source):
        title = self.clean_text(job_data.get("title", ""))
        apply_url = (job_data.get("apply_url", "") or "").strip()

        if not title or not apply_url:
            return False

        _, created = Job.objects.update_or_create(
            source=source,
            apply_url=apply_url,
            defaults={
                "title": title[:200],
                "company": self.clean_text(job_data.get("company", source.name))[:200],
                "location": self.clean_text(job_data.get("location", "Bangladesh"))[:200],
                "work_mode": job_data.get("work_mode", "onsite"),
                "job_type": job_data.get("job_type", "full_time"),
                "deadline": job_data.get("deadline"),
                "description": self.clean_text(job_data.get("description", ""))[:2000],
                "is_active": True,
            },
        )
        return created