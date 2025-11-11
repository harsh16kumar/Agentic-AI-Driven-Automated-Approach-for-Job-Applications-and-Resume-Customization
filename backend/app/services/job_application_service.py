import os
import json
import time
from typing import List, Dict
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class JobApplicationService:
    """
    Automates job applications using Selenium.
    Handles LinkedIn Easy Apply and basic application forms.
    """
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None
        self.applications_log_path = "data/applications_log.json"
        os.makedirs("data", exist_ok=True)
    
    def init_driver(self):
        """Initialize Selenium WebDriver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Set user agent to appear more human
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()
    
    def close_driver(self):
        """Close the WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def login_linkedin(self, email: str, password: str) -> bool:
        """Login to LinkedIn."""
        try:
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(2)
            
            email_field = self.driver.find_element(By.ID, "username")
            password_field = self.driver.find_element(By.ID, "password")
            
            email_field.send_keys(email)
            password_field.send_keys(password)
            
            login_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_btn.click()
            
            time.sleep(5)
            
            # Check if login successful
            if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
                print("✅ LinkedIn login successful")
                return True
            else:
                print("❌ LinkedIn login failed")
                return False
        
        except Exception as e:
            print(f"❌ LinkedIn login error: {e}")
            return False
    
    def apply_linkedin_easy_apply(self, job_url: str, user_data: dict) -> bool:
        """
        Apply to a LinkedIn job using Easy Apply.
        Handles multi-step forms.
        """
        try:
            self.driver.get(job_url)
            time.sleep(3)
            
            # Click Easy Apply button
            easy_apply_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label*='Easy Apply']"))
            )
            easy_apply_btn.click()
            time.sleep(2)
            
            # Handle multi-step form
            max_steps = 10
            step = 0
            
            while step < max_steps:
                step += 1
                
                # Fill in form fields
                try:
                    # Phone number
                    phone_input = self.driver.find_element(By.CSS_SELECTOR, "input[id*='phoneNumber']")
                    if phone_input.get_attribute("value") == "":
                        phone_input.send_keys(user_data.get("contact", {}).get("phone", ""))
                except NoSuchElementException:
                    pass
                
                # Check for Next or Submit button
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "button[aria-label='Continue to next step']")
                    next_btn.click()
                    time.sleep(2)
                except NoSuchElementException:
                    # Try to find Submit button
                    try:
                        submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[aria-label='Submit application']")
                        submit_btn.click()
                        time.sleep(3)
                        print("✅ Application submitted!")
                        return True
                    except NoSuchElementException:
                        # Try generic submit
                        try:
                            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                            submit_btn.click()
                            time.sleep(3)
                            return True
                        except:
                            break
            
            print("⚠️ Could not complete application (multi-step issue)")
            return False
        
        except Exception as e:
            print(f"❌ LinkedIn Easy Apply error: {e}")
            return False
    
    def apply_generic_form(self, job_url: str, user_data: dict) -> bool:
        """
        Apply to jobs via generic application forms.
        Attempts to fill common fields.
        """
        try:
            self.driver.get(job_url)
            time.sleep(3)
            
            # Try to find and fill common form fields
            contact = user_data.get("contact", {})
            
            # Name
            try:
                name_field = self.driver.find_element(By.CSS_SELECTOR, "input[name*='name'], input[id*='name']")
                name_field.send_keys(user_data.get("name", ""))
            except NoSuchElementException:
                pass
            
            # Email
            try:
                email_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='email'], input[name*='email']")
                email_field.send_keys(contact.get("email", ""))
            except NoSuchElementException:
                pass
            
            # Phone
            try:
                phone_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='tel'], input[name*='phone']")
                phone_field.send_keys(contact.get("phone", ""))
            except NoSuchElementException:
                pass
            
            # LinkedIn URL
            try:
                linkedin_field = self.driver.find_element(By.CSS_SELECTOR, "input[name*='linkedin']")
                linkedin_field.send_keys(contact.get("linkedin", ""))
            except NoSuchElementException:
                pass
            
            # Try to find and click submit button
            try:
                submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                submit_btn.click()
                time.sleep(3)
                print("✅ Generic form submitted!")
                return True
            except NoSuchElementException:
                print("⚠️ Could not find submit button")
                return False
        
        except Exception as e:
            print(f"❌ Generic form error: {e}")
            return False
    
    def apply_to_jobs(self, jobs: List[Dict], user_data: dict, linkedin_email: str = None, linkedin_password: str = None, max_applications: int = 5) -> List[Dict]:
        """
        Main method to apply to multiple jobs.
        Returns list of application results.
        """
        results = []
        self.init_driver()
        
        # Login to LinkedIn if credentials provided
        linkedin_logged_in = False
        if linkedin_email and linkedin_password:
            linkedin_logged_in = self.login_linkedin(linkedin_email, linkedin_password)
        
        applied_count = 0
        
        for job in jobs:
            if applied_count >= max_applications:
                break
            
            job_url = job.get("apply_link", "")
            if not job_url:
                continue
            
            result = {
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job_url,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed"
            }
            
            try:
                # Determine application method
                if "linkedin.com" in job_url and linkedin_logged_in:
                    success = self.apply_linkedin_easy_apply(job_url, user_data)
                else:
                    success = self.apply_generic_form(job_url, user_data)
                
                if success:
                    result["status"] = "success"
                    applied_count += 1
                    print(f"✅ Applied to: {job.get('title')} at {job.get('company')}")
                else:
                    result["status"] = "partial"
                    print(f"⚠️ Partial/failed: {job.get('title')} at {job.get('company')}")
            
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                print(f"❌ Error applying to {job.get('title')}: {e}")
            
            results.append(result)
            time.sleep(5)  # Rate limiting
        
        self.close_driver()
        
        # Save application log
        self.save_application_log(results)
        
        return results
    
    def save_application_log(self, results: List[Dict]):
        """Save application results to log file."""
        # Load existing log
        if os.path.exists(self.applications_log_path):
            with open(self.applications_log_path, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        else:
            log_data = {"applications": []}
        
        # Append new results
        log_data["applications"].extend(results)
        
        # Save
        with open(self.applications_log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        
        print(f"Application log saved to {self.applications_log_path}")
    
    def get_application_history(self) -> List[Dict]:
        """Retrieve application history."""
        if not os.path.exists(self.applications_log_path):
            return []
        
        with open(self.applications_log_path, "r", encoding="utf-8") as f:
            log_data = json.load(f)
        
        return log_data.get("applications", [])