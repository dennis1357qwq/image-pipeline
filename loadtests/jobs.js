import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";
import exec from "k6/execution";
import { IMAGE_FILES, PROFILES, TASKS } from "./profiles.js";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.1/index.js";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const RATE = Number(__ENV.RATE || "2");
const DURATION = __ENV.DURATION || "1m";
const PROFILE = __ENV.PROFILE || "representative_mixed";
const POLL_RESULT = (__ENV.POLL_RESULT || "true") === "true";
const POLL_INTERVAL_SECONDS = Number(__ENV.POLL_INTERVAL_SECONDS || "1");
const POLL_TIMEOUT_SECONDS = Number(__ENV.POLL_TIMEOUT_SECONDS || "60");

function buildArrivalRate(ratePerSecond) {
  if (!Number.isFinite(ratePerSecond) || ratePerSecond <= 0) {
    throw new Error(`RATE must be a positive number, got: ${ratePerSecond}`);
  }

  if (Number.isInteger(ratePerSecond)) {
    return {
      rate: ratePerSecond,
      timeUnit: "1s",
    };
  }

  return {
    rate: Math.max(1, Math.round(ratePerSecond * 60)),
    timeUnit: "1m",
  };
}

const arrivalRate = buildArrivalRate(RATE);

function logK6Error(event, details = {}) {
  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      event,
      source: "k6",
      ...details,
    }),
  );
}

const images = {};
for (const [size, path] of Object.entries(IMAGE_FILES)) {
  images[size] = open(`../${path}`, "b");
}

export const options = {
  scenarios: {
    submit_jobs: {
      executor: "constant-arrival-rate",
      rate: arrivalRate.rate,
      timeUnit: arrivalRate.timeUnit,
      duration: DURATION,
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
};

const submittedJobs = new Counter("submitted_jobs");
const completedJobs = new Counter("completed_jobs");
const failedJobs = new Counter("failed_jobs");
const rejectedJobs = new Counter("rejected_jobs");
const endToEndTime = new Trend("end_to_end_time_ms");
const pollCount = new Trend("poll_count");

const taskMetrics = {};

for (const taskName of Object.keys(TASKS)) {
  taskMetrics[taskName] = {
    submitted: new Counter(`task_${taskName}_submitted`),
    completed: new Counter(`task_${taskName}_completed`),
    failed: new Counter(`task_${taskName}_failed`),
    rejected: new Counter(`task_${taskName}_rejected`),
    endToEndTime: new Trend(`task_${taskName}_end_to_end_time_ms`),
  };
}

function selectTask() {
  const profile = PROFILES[PROFILE];

  if (!profile) {
    throw new Error(`Unknown PROFILE: ${PROFILE}`);
  }

  const totalWeight = profile.reduce((sum, entry) => sum + entry.weight, 0);
  let randomValue = Math.random() * totalWeight;

  for (const entry of profile) {
    randomValue -= entry.weight;
    if (randomValue <= 0) {
      const task = TASKS[entry.task];

      if (!task) {
        throw new Error(`Unknown task in profile: ${entry.task}`);
      }

      return {
        name: entry.task,
        class: task.class,
        imageSize: task.imageSize,
        pipeline: JSON.stringify(task.pipeline),
        image: images[task.imageSize],
      };
    }
  }

  const fallback = profile[profile.length - 1];
  const task = TASKS[fallback.task];

  return {
    name: fallback.task,
    class: task.class,
    imageSize: task.imageSize,
    pipeline: JSON.stringify(task.pipeline),
    image: images[task.imageSize],
  };
}

function pollUntilDone(jobId, startTime, taskTags) {
  let polls = 0;
  const deadline = Date.now() + POLL_TIMEOUT_SECONDS * 1000;

  while (Date.now() < deadline) {
    sleep(POLL_INTERVAL_SECONDS);
    polls += 1;

    const response = http.get(`${BASE_URL}/jobs/${jobId}`);

    if (response.status !== 200) {
      logK6Error("poll_http_error", {
        job_id: jobId,
        status_code: response.status,
      });

      failedJobs.add(1, taskTags);
      pollCount.add(polls, taskTags);
      return;
    }

    const body = response.json();

    if (body.status === "DONE") {
      completedJobs.add(1, taskTags);
      endToEndTime.add(Date.now() - startTime, taskTags);
      pollCount.add(polls, taskTags);
      taskMetrics[taskTags.task].completed.add(1);
      taskMetrics[taskTags.task].endToEndTime.add(Date.now() - startTime);
      return;
    }

    if (body.status === "FAILED") {
      logK6Error("job_failed", {
        job_id: jobId,
        message: body.error || body.message || "",
      });

      failedJobs.add(1, taskTags);
      pollCount.add(polls, taskTags);
      taskMetrics[taskTags.task].failed.add(1);
      return;
    }
  }

  logK6Error("poll_timeout", {
    job_id: jobId,
    timeout_seconds: POLL_TIMEOUT_SECONDS,
    polls,
  });

  failedJobs.add(1, taskTags);
  pollCount.add(polls, taskTags);
  taskMetrics[taskTags.task].failed.add(1);
}

export default function () {
  const task = selectTask();
  const startTime = Date.now();
  const taskTags = {
    task: task.name,
    class: task.class,
    image_size: task.imageSize,
  };

  const payload = {
    pipeline: task.pipeline,
    file: http.file(task.image, `${task.imageSize}.png`, "image/png"),
  };

  const response = http.post(`${BASE_URL}/jobs`, payload);

  const ok = check(response, {
    "job submitted": (r) => r.status === 200,
  });

  if (!ok) {
    logK6Error(response.status === 429 ? "job_rejected" : "submit_http_error", {
      status_code: response.status,
      task: task.name,
      response_body: response.body,
    });

    if (response.status === 429) {
      rejectedJobs.add(1, taskTags);
      taskMetrics[task.name].rejected.add(1);
    } else {
      failedJobs.add(1, taskTags);
      taskMetrics[task.name].failed.add(1);
    }
    return;
  }

  submittedJobs.add(1, taskTags);
  taskMetrics[task.name].submitted.add(1);

  const body = response.json();

  if (POLL_RESULT) {
    pollUntilDone(body.job_id, startTime, taskTags);
  }
}

export function handleSummary(data) {
  const outputPath = __ENV.WORKLOAD_SUMMARY_PATH || "workload_summary.json";

  const submittedByTask = {};
  const completedByTask = {};
  const failedByTask = {};
  const rejectedByTask = {};

  for (const taskName of Object.keys(TASKS)) {
    submittedByTask[taskName] =
      data.metrics[`task_${taskName}_submitted`]?.values?.count || 0;

    completedByTask[taskName] =
      data.metrics[`task_${taskName}_completed`]?.values?.count || 0;

    failedByTask[taskName] =
      data.metrics[`task_${taskName}_failed`]?.values?.count || 0;

    rejectedByTask[taskName] =
      data.metrics[`task_${taskName}_rejected`]?.values?.count || 0;
  }

  const workloadSummary = {
    profile: PROFILE,
    rate: RATE,
    duration: DURATION,
    poll_result: POLL_RESULT,
    submitted_by_task: submittedByTask,
    completed_by_task: completedByTask,
    failed_by_task: failedByTask,
    rejected_by_task: rejectedByTask,
    k6_metrics: data.metrics,
  };

  return {
    stdout: textSummary(data),
    [outputPath]: JSON.stringify(workloadSummary, null, 2),
  };
}
