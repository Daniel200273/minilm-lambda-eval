"""
Burst traffic (Report Test 2, and the driver for Tests 5 and 6).

Every simulated user fires exactly ONE request, then stops. With
`-u N -r N` all N users spawn within ~1 second, approximating N
simultaneous requests.

Not run directly - invoke through ../run_experiment.sh, which records the
UTC time window needed to correlate with CloudWatch afterwards.
"""
import random

from locust import HttpUser, task
from locust.exception import StopUser

from common import ENDPOINT_PATH, STATS_NAME, TOP_K, load_questions

QUESTIONS = load_questions()


class BurstUser(HttpUser):
    @task
    def fire_once(self):
        q = random.choice(QUESTIONS)
        self.client.post(
            ENDPOINT_PATH,
            json={"query": q["question"], "top_k": TOP_K},
            name=STATS_NAME,
        )
        raise StopUser()
