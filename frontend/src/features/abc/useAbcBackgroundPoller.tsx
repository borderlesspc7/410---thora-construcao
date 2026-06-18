import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { pingApiHealth } from "../../services/api";
import { getAbcBatchStatus, type AbcAnalysisJob } from "../../services/abcAnalysis";
import {
  loadActiveAbcJobs,
  markAbcJobNotified,
  untrackAbcBackgroundJob,
  wasAbcJobNotified,
} from "./abcBackgroundJobs";

const POLL_MS = 5000;

export function useAbcBackgroundPoller(): void {
  const navigate = useNavigate();
  const pollingRef = useRef(false);
  const slowPollRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      if (pollingRef.current) return;
      const uploadIds = loadActiveAbcJobs();
      if (uploadIds.length === 0) return;

      pollingRef.current = true;
      try {
        const apiUp = await pingApiHealth(slowPollRef.current ? 6 : 3);
        if (!apiUp || cancelled) {
          slowPollRef.current = true;
          return;
        }
        slowPollRef.current = false;

        const jobs = (await getAbcBatchStatus(uploadIds)) ?? [];
        if (cancelled) return;

        for (const job of jobs) {
          handleTerminalJob(job, navigate);
        }

        const stillActive = jobs.some((job) =>
          ["queued", "processing", "uploading", "detecting"].includes(job.status),
        );
        const tracked = loadActiveAbcJobs();
        if (!stillActive && tracked.length === 0) {
          return;
        }
      } catch {
        slowPollRef.current = true;
      } finally {
        pollingRef.current = false;
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [navigate]);
}

function handleTerminalJob(job: AbcAnalysisJob, navigate: ReturnType<typeof useNavigate>): void {
  if (job.status !== "completed" && job.status !== "failed") {
    return;
  }
  if (wasAbcJobNotified(job.upload_id)) {
    untrackAbcBackgroundJob(job.upload_id);
    return;
  }

  markAbcJobNotified(job.upload_id);
  untrackAbcBackgroundJob(job.upload_id);

  if (job.status === "completed") {
    const itemsLabel =
      typeof job.items_found === "number" && job.items_found > 0
        ? `${job.items_found} item(ns) salvos`
        : "PDF e itens salvos";
    toast.success(`Análise concluída: ${job.filename}`, {
      description: `Na Lista de análises — ${itemsLabel}.`,
      duration: 12000,
      action: {
        label: "Abrir validação",
        onClick: () => navigate(`/validacao/${job.upload_id}`),
      },
    });
    return;
  }

  toast.error(`Falha na análise: ${job.filename}`, {
    description: job.error || job.message || "Tente novamente na Lista de análises.",
    duration: 10000,
    action: {
      label: "Ver fila",
      onClick: () => navigate("/lista-analises"),
    },
  });
}
