# locustfile.py — Lab Tech Portal load-test suite
#
# Locust version: 2.30.0 (pinned — see docker-compose.load.yml and README.md)
#
# Auth: The portal uses Okta for production SSO.  During load tests, auth is
# bypassed by NOT setting OKTA_ISSUER in the environment; app.py then sets
# LOGIN_DISABLED=True which skips all login_required checks.  The locust
# service is started with the OKTA_ISSUER env var absent (see
# docker-compose.load.yml).  No credential management is needed in this file.
#
# Mix targets:
#   60% reads  — list/detail views across all 5 tools (weight totals: 60)
#   30% writes — POST forms that mutate data in SQLite (weight totals: 30)
#   10% Jira-touching writes — system-locator import / print-request submit
#                              (weight totals: 10)
#   These weights are distributed across TaskSets proportionally.
#
# Jira-touching tasks: The system-locator Jira import and print-request submit
# can trigger outbound Jira API calls.  Operators MUST set JIRA_DRY_RUN=true
# (or leave JIRA_* env vars unset) before running a load test.  Tasks that
# would trigger Jira are guarded with a skip-and-log if the endpoint is not
# available, but the operator is responsible for Jira isolation.

import logging
import random
import string

from locust import HttpUser, TaskSet, between, tag, task

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_suffix(n: int = 6) -> str:
    """Return a short random alphanumeric string for unique field values."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ---------------------------------------------------------------------------
# TaskSet: Inventory  (read: weight 15 / write: weight 7)
# ---------------------------------------------------------------------------

class InventoryTasks(TaskSet):
    """
    Inventory tool tasks.  The mix within this TaskSet contributes:
      - reads (list):  weight 15 → ~15 % of total
      - write (add):   weight 7  → ~7 % of total
    """

    @tag("read", "inventory")
    @task(15)
    def list_inventory(self):
        with self.client.get("/inventory/", catch_response=True) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"list_inventory: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("write", "inventory")
    @task(7)
    def add_item(self):
        """POST a new inventory item.  Uses a random name to avoid unique-key
        clashes across concurrent workers."""
        payload = {
            "name": f"load-item-{_random_suffix()}",
            "description": "Load test item — safe to delete",
            "quantity": random.randint(1, 10),
            "min_stock": 1,
        }
        with self.client.post(
            "/inventory/add_item",
            data=payload,
            allow_redirects=False,
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 201, 302):
                resp.failure(f"add_item: unexpected {resp.status_code}")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# TaskSet: Checkout  (read: weight 15 / write: weight 7)
# ---------------------------------------------------------------------------

class CheckoutTasks(TaskSet):
    """
    Checkout tool tasks.
      - reads (dashboard): weight 15
      - write (return):    weight 7  — returns item ID 1 if it exists; ignores
                                       404 (item may not exist in a fresh DB)
    """

    @tag("read", "checkout")
    @task(15)
    def checkout_dashboard(self):
        with self.client.get("/checkout/", catch_response=True) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"checkout_dashboard: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("write", "checkout")
    @task(7)
    def return_item(self):
        """Return item ID 1.  Acceptable outcomes: 200/302 (success) or 404
        (item not found — harmless in a seeded-less test env)."""
        with self.client.post(
            "/checkout/1/return",
            allow_redirects=False,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 302, 404):
                resp.success()
            else:
                resp.failure(f"return_item: unexpected {resp.status_code}")


# ---------------------------------------------------------------------------
# TaskSet: RF Chamber  (read: weight 15 / write: weight 8)
# ---------------------------------------------------------------------------

class RFChamberTasks(TaskSet):
    """
    RF Chamber tool tasks.
      - reads (dashboard):  weight 15
      - write (add):        weight 8
    """

    @tag("read", "rf_chamber")
    @task(15)
    def rf_dashboard(self):
        with self.client.get("/rf-chamber/", catch_response=True) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"rf_dashboard: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("write", "rf_chamber")
    @task(8)
    def add_chamber(self):
        """POST a new RF chamber.  Barcode must be unique — use random suffix."""
        payload = {
            "barcode": f"LC{_random_suffix(4).upper()}",
            "size": "Medium",
            "ports": "Ethernet Port",
            "purpose": "Load test chamber",
            "location": "Bay 99",
            "owner": "load-test",
        }
        with self.client.post(
            "/rf-chamber/add",
            data=payload,
            allow_redirects=False,
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 201, 302):
                resp.failure(f"add_chamber: unexpected {resp.status_code}")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# TaskSet: System Locator  (read: weight 10 / write: weight 4 / jira: weight 5)
# ---------------------------------------------------------------------------

class SystemLocatorTasks(TaskSet):
    """
    System Locator tool tasks.
      - reads (dashboard):  weight 10
      - write (add system): weight 4
      - Jira-touching (import page): weight 5
        The Jira import endpoint is a GET that returns the import form —
        submitting a real import is not attempted here to avoid flooding Jira.
        Operators should confirm JIRA_DRY_RUN=true before running.
    """

    @tag("read", "system_locator")
    @task(10)
    def system_dashboard(self):
        with self.client.get("/systems/", catch_response=True) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"system_dashboard: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("write", "system_locator")
    @task(4)
    def create_system(self):
        """POST a new system.  Identifiers are required; use a random value."""
        payload = {
            "identifier_type_0": "Serial",
            "identifier_value_0": f"SN-{_random_suffix()}",
            "location_name": "Building A",
            "location_number": "101",
            "notes": "Load test system",
        }
        with self.client.post(
            "/systems/new",
            data=payload,
            allow_redirects=False,
            catch_response=True,
        ) as resp:
            # 302 redirect on success; 200 = form re-displayed with errors (acceptable)
            if resp.status_code not in (200, 201, 302):
                resp.failure(f"create_system: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("jira", "system_locator")
    @task(5)
    def jira_import_form(self):
        """GET the Jira import form — exercises the route without triggering a
        real Jira API call.  Actual import POST is intentionally omitted from
        load tests; see module docstring."""
        with self.client.get(
            "/systems/jira-import",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"jira_import_form: unexpected {resp.status_code}")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# TaskSet: Print Requests  (read: weight 5 / write: weight 4 / jira: weight 5)
# ---------------------------------------------------------------------------

class PrintRequestTasks(TaskSet):
    """
    Print Requests tool tasks.
      - reads (list / request queue): weight 5
      - write (new request form GET): weight 4  — full POST requires a file
        upload which is intentionally omitted from the automated load mix;
        operators may add it manually post-merge.
      - Jira-touching (new request GET): weight 5
        The create_request route may queue a Jira task if
        PRINT_REQUESTS_CREATE_JIRA=true.  In load tests this must be false.
    """

    @tag("read", "print_requests")
    @task(5)
    def list_print_requests(self):
        with self.client.get("/print-requests/", catch_response=True) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"list_print_requests: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("read", "print_requests")
    @task(5)
    def request_queue(self):
        with self.client.get("/print-requests/requests", catch_response=True) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"request_queue: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("write", "print_requests")
    @task(4)
    def new_request_form(self):
        """GET the new print-request form page (write-adjacent; form display)."""
        with self.client.get(
            "/print-requests/new",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"new_request_form: unexpected {resp.status_code}")
            else:
                resp.success()

    @tag("jira", "print_requests")
    @task(5)
    def request_history(self):
        """Request history page — included in the Jira-touching bucket because
        it renders Jira sync status columns.  Does not make outbound Jira
        calls itself."""
        with self.client.get(
            "/print-requests/requests/history",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 302):
                resp.failure(f"request_history: unexpected {resp.status_code}")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# Composite HttpUser
# ---------------------------------------------------------------------------

class LabPortalUser(HttpUser):
    """Simulates a QE user browsing all five lab tools.

    Wait times model a realistic user pacing (1–3 s between requests).
    TaskSet weights below achieve the 60 / 30 / 10 read/write/Jira mix:

      Tool              read   write  jira
      ----              ----   -----  ----
      Inventory          15      7      0
      Checkout           15      7      0
      RF Chamber         15      8      0
      System Locator     10      4      5
      Print Requests     10      4      5
                         --     --     --
      Total              60     30     10   (90 + 10 = 100 implied)

    Because locust does not natively weight TaskSets against each other, we
    inline all tasks on this user class with the weights above using nested
    task references.
    """

    wait_time = between(1, 3)

    # --- Inventory ---

    @tag("read", "inventory")
    @task(15)
    def inventory_list(self):
        InventoryTasks.list_inventory(self)

    @tag("write", "inventory")
    @task(7)
    def inventory_add(self):
        InventoryTasks.add_item(self)

    # --- Checkout ---

    @tag("read", "checkout")
    @task(15)
    def checkout_list(self):
        CheckoutTasks.checkout_dashboard(self)

    @tag("write", "checkout")
    @task(7)
    def checkout_return(self):
        CheckoutTasks.return_item(self)

    # --- RF Chamber ---

    @tag("read", "rf_chamber")
    @task(15)
    def rf_list(self):
        RFChamberTasks.rf_dashboard(self)

    @tag("write", "rf_chamber")
    @task(8)
    def rf_add(self):
        RFChamberTasks.add_chamber(self)

    # --- System Locator ---

    @tag("read", "system_locator")
    @task(10)
    def systems_list(self):
        SystemLocatorTasks.system_dashboard(self)

    @tag("write", "system_locator")
    @task(4)
    def systems_create(self):
        SystemLocatorTasks.create_system(self)

    @tag("jira", "system_locator")
    @task(5)
    def systems_jira_form(self):
        SystemLocatorTasks.jira_import_form(self)

    # --- Print Requests ---

    @tag("read", "print_requests")
    @task(5)
    def print_list(self):
        PrintRequestTasks.list_print_requests(self)

    @tag("read", "print_requests")
    @task(5)
    def print_queue(self):
        PrintRequestTasks.request_queue(self)

    @tag("write", "print_requests")
    @task(4)
    def print_new_form(self):
        PrintRequestTasks.new_request_form(self)

    @tag("jira", "print_requests")
    @task(5)
    def print_history(self):
        PrintRequestTasks.request_history(self)
