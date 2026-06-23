/** 后台任务 REST API */
import { api } from "./http.js";

export async function fetchJobs({ page = 1, page_size = 15, job_type } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (job_type) q.set("job_type", job_type);
  return api(`/api/v1/jobs?${q}`);
}

export async function fetchJob(jobId) {
  return api(`/api/v1/jobs/${jobId}`);
}

export async function clearJobs(scope = "finished") {
  const q = new URLSearchParams({ scope });
  return api(`/api/v1/jobs/clear?${q}`, { method: "DELETE" });
}

export async function cancelJob(jobId) {
  return api(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function batchDeleteJobs(jobIds) {
  return api("/api/v1/jobs/batch-delete", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds }),
  });
}
