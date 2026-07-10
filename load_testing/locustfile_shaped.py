"""
Trapezoidal load shape. Drives two experiments from the report:

  Test 3  Steady traffic          (short ramp, hold at peak, ramp down)
  Test 9  Cold-start ramp-up      (long ramp, long hold, for the time-series plot)

wait_time = constant_throughput(RPS_PER_USER) means each simulated user
attempts exactly RPS_PER_USER requests per second. With the default of 1.0,
PEAK_USERS maps directly onto the report's "peak req/s" column, which is
what Table 5 needs. (Locust cannot exceed this if the response time is
longer than 1/RPS_PER_USER - under heavy throttling the achieved rate will
fall below the target, which is itself a result worth reporting.)

SPAWN_RATE is the report's "step size": users added per second while ramping.

Environment variables:
  PEAK_USERS     target concurrent users at plateau   (default 25)
  RAMP_SECONDS   seconds to ramp 0 -> peak            (default 15)
  HOLD_SECONDS   seconds held at peak                 (default 30)
  SPAWN_RATE     users added per second ("step size") (default 5)
  RPS_PER_USER   requests/sec each user attempts      (default 1.0)
  plus VARIANT / QUESTION_BUCKET / TOP_K from common.py

Total runtime = 2*RAMP_SECONDS + HOLD_SECONDS.

Not run directly - invoke through ../run_experiment.sh.
"""
import os
import random

from locust import HttpUser, LoadTestShape, constant_throughput, task

from common import ENDPOINT_PATH, STATS_NAME, TOP_K, load_questions

QUESTIONS = load_questions()

PEAK_USERS = int(os.environ.get("PEAK_USERS", "25"))
RAMP_SECONDS = int(os.environ.get("RAMP_SECONDS", "15"))
HOLD_SECONDS = int(os.environ.get("HOLD_SECONDS", "30"))
SPAWN_RATE = int(os.environ.get("SPAWN_RATE", "5"))
RPS_PER_USER = float(os.environ.get("RPS_PER_USER", "1.0"))


class SearchUser(HttpUser):
    wait_time = constant_throughput(RPS_PER_USER)

    @task
    def search(self):
        q = random.choice(QUESTIONS)
        self.client.post(
            ENDPOINT_PATH,
            json={"query": q["question"], "top_k": TOP_K},
            name=STATS_NAME,
        )


class TrapezoidShape(LoadTestShape):
    """Ramp up -> hold -> ramp down. Returning None ends the test."""

    def tick(self):
        t = self.get_run_time()
        total = RAMP_SECONDS * 2 + HOLD_SECONDS

        if t > total:
            return None

        if t < RAMP_SECONDS:
            users = max(1, int((t / RAMP_SECONDS) * PEAK_USERS))
        elif t < RAMP_SECONDS + HOLD_SECONDS:
            users = PEAK_USERS
        else:
            remaining = total - t
            users = max(1, int((remaining / RAMP_SECONDS) * PEAK_USERS))

        return (users, SPAWN_RATE)
