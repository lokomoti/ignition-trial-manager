import os
import time
from datetime import datetime

from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


USERNAME = os.getenv("USERNAME", "admin")
PASSWORD = os.getenv("PASSWORD", "password")
RESET_INTERVAL_SECONDS = int(os.getenv("RESETINTERVAL", "5"))
TARGET_GATEWAY = os.getenv("TARGET_GATEWAY", "http://host.docker.internal")
TARGET_GATEWAY_PORT = os.getenv("TARGET_GATEWAY_PORT", "8088")

CONTAINER_INTERNAL_URL = f"{TARGET_GATEWAY}:{TARGET_GATEWAY_PORT}"  # Gateway URL as seen from the Selenium container
SELENIUM_CONTAINER_URL = "http://host.docker.internal:4444"
# SELENIUM_CONTAINER_URL = "http://localhost:4444"  # Used for testing


class LoginError(Exception):
    """Raised when login failed."""


class NotAuthorizedToRestartError(Exception):
    """Raised when user is not authorized to restart trial."""


def get_driver() -> WebDriver:
    """Get webdriver instance."""

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")

    return webdriver.Remote(command_executor=SELENIUM_CONTAINER_URL, options=options)


def _parse_countdown(countdown_string: str) -> int:
    """Parse countdown timer from string to seconds."""
    time_obj = datetime.strptime(countdown_string, "%H:%M:%S")
    seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second

    return seconds


def get_time_remaining(driver: WebDriver) -> int:
    """Perform trial restart operations."""
    remaining_time = driver.find_element(By.CLASS_NAME, "countdown").text

    return _parse_countdown(remaining_time)


def click_restart_trial(driver: WebDriver):
    """Click restart trial button."""
    reset_button = driver.find_element(By.ID, "reset-trial-anchor")

    if reset_button.text == "Reset Trial":
        reset_button.click()
    else:
        raise NotAuthorizedToRestartError(
            "User is not authorized to restart the trial. Make sure user has Administrator role."
        )


def get_logged_in_user(driver: WebDriver, timeout: int) -> str | None:
    """Attempt to read a div that contains logged in username."""

    try:
        logged_in_user = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.user-info span:not([class])")
            )
        )

        return logged_in_user.text

    except TimeoutException:
        return None


def login(driver: WebDriver):
    """Login with provided credentials."""
    driver.find_element(By.ID, "login-link").click()
    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.CLASS_NAME, "submit-button").click()
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)
    driver.find_element(By.CLASS_NAME, "submit-button").click()

    logged_in_user = get_logged_in_user(driver, timeout=5)

    if logged_in_user == USERNAME:
        logger.info(f"User '{USERNAME}' logged in successfully.")
    else:
        raise LoginError(
            f"Logging in failed with credentials: '{USERNAME}': '{PASSWORD}'"
        )


def run_restart_process():
    """Run restart process."""

    driver = get_driver()

    try:
        driver.get(CONTAINER_INTERNAL_URL)
        driver.implicitly_wait(1)
        seconds_remaining = get_time_remaining(driver)

        if seconds_remaining == 0:
            logger.info("Trial Expired.")

            if get_logged_in_user(driver, timeout=1) is None:
                logger.info("Login Required.")
                login(driver)

            click_restart_trial(driver)
            logger.success(f"Time remaining: {get_time_remaining(driver)}")
        else:
            logger.info(f"Time remaining: {seconds_remaining}")
    finally:
        driver.quit()


def main():

    while True:
        try:
            run_restart_process()
        except Exception as e:
            logger.error(f"{e}")
        time.sleep(RESET_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
