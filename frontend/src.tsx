import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  Film,
  Heart,
  History,
  Home,
  Library,
  MessageCircle,
  Play,
  Plus,
  Settings,
  Upload,
  Users,
  X,
} from "lucide-react";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import "./style.css";
import "./library.css";
import "./accounts.css";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const apiUrl = (path: string) => `${apiBaseUrl}/api${path}`;
const api = (path: string, options?: RequestInit) => {
  const effectivePath =
    path.endsWith("/generate-schedule") && options?.method === "POST"
      ? path.replace("/generate-schedule", "/start-generation")
      : path;
  return fetch(apiUrl(effectivePath), {
    credentials: "include",
    ...options,
    // Os cartões e o ranking mudam com o período. Não reutilizamos uma
    // resposta GET antiga do navegador quando o usuário troca o filtro.
    cache: "no-store",
  }).then(async (response) => {
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  });
};
const pages = [
  ["Início", Home],
  ["Biblioteca", Library],
  ["Contas", Users],
  ["Campanhas", Play],
  ["Histórico", History],
  ["Configurações", Settings],
] as const;
const pagePaths: Record<string, string> = {
  Início: "/",
  Biblioteca: "/biblioteca",
  Contas: "/contas",
  Campanhas: "/campanhas",
  Histórico: "/historico",
  Configurações: "/configuracoes",
};

const localDate = () => {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
};
// Eventos do servidor são gravados em UTC; horários da agenda já são locais.
const eventDate = (value: string) =>
  new Date(value.endsWith("Z") ? value : `${value}Z`).toLocaleString("pt-BR");
const statusLabel = (status: string) =>
  ({
    PENDING: "AGENDADO",
    CLAIMED: "PROCESSANDO",
    UPLOADING: "PROCESSANDO",
    WAITING_META: "PROCESSANDO",
    PUBLISHING: "PROCESSANDO",
    PUBLISHED: "PUBLICADO",
    FAILED: "FALHOU",
    SKIPPED: "PULADO",
    CANCELLED: "CANCELADO",
    PAUSED: "PAUSADO",
  })[status] || status;
const defaultCampaignName = (
  start: string,
  days: number,
  intervals: string[],
) => {
  const first = new Date(`${start}T12:00:00`);
  const last = new Date(first);
  last.setDate(last.getDate() + Math.max(1, days) - 1);
  const fmt = (value: Date) =>
    `${String(value.getDate()).padStart(2, "0")}/${String(value.getMonth() + 1).padStart(2, "0")}`;
  return `${fmt(first)}-${fmt(last)} · ${intervals.length} mídia(s)/dia`;
};
const campaignEndDate = (start: string, days: number) => {
  const end = new Date(`${start}T12:00:00`);
  end.setDate(end.getDate() + Math.max(1, days) - 1);
  return end.toLocaleDateString("pt-BR");
};
const agendaDateKey = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const page =
    Object.entries(pagePaths).find(
      ([, path]) => path === location.pathname,
    )?.[0] || "Início";
  const setPage = (label: string) => navigate(pagePaths[label] || "/");
  useEffect(() => {
    if (["/agenda", "/insights"].includes(location.pathname))
      navigate("/", { replace: true });
  }, [location.pathname, navigate]);
  const [dashboard, setDashboard] = useState<any>({});
  const [accounts, setAccounts] = useState<any[]>([]);
  const [media, setMedia] = useState<any[]>([]);
  const [agenda, setAgenda] = useState<any[]>([]);
  const [agendaMonth, setAgendaMonth] = useState(
    () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [agendaDay, setAgendaDay] = useState(agendaDateKey(new Date()));
  const [activity, setActivity] = useState<any[]>([]);
  const [activitySummary, setActivitySummary] = useState<any>({});
  const [insights, setInsights] = useState<any>({ reels: [], accounts: [] });
  const [insightPeriod, setInsightPeriod] = useState("total");
  const [insightsUpdating, setInsightsUpdating] = useState(false);
  const [homePeriod, setHomePeriod] = useState("total");
  const [homeInsights, setHomeInsights] = useState<any>({
    reels: [],
    summary: {},
  });
  const [viewsChart, setViewsChart] = useState<any>({ points: [] });
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [scripts, setScripts] = useState<any[]>([]);
  const [captionLists, setCaptionLists] = useState<any[]>([]);
  const [captionListId, setCaptionListId] = useState<number | null>(null);
  const [captionText, setCaptionText] = useState("");
  const [defaults, setDefaults] = useState<any>({
    intervals: ["11:00-13:00"],
    days: 7,
    strategy: "sequential",
    script_ids: [],
    cover_path: "",
    caption_list_id: null,
    caption_text: "",
  });
  const [accountSyncDelay, setAccountSyncDelay] = useState(1);
  const [coverPath, setCoverPath] = useState("");
  const [coverName, setCoverName] = useState("");
  const [tunnel, setTunnel] = useState<any>({});
  const [notice, setNotice] = useState("");
  const [campaignOpen, setCampaignOpenState] = useState(false);
  const [campaignName, setCampaignName] = useState("");
  const [campaignDescription, setCampaignDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [setupCampaign, setSetupCampaign] = useState<any>(null);
  const [setupAccounts, setSetupAccounts] = useState<number[]>([]);
  const [setupMedia, setSetupMedia] = useState<number[]>([]);
  const [setupScripts, setSetupScripts] = useState<number[]>([]);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [email, setEmail] = useState("hotdavinci@gmail.com");
  const [password, setPassword] = useState("");
  const [scheduleModal, setScheduleModal] = useState<any>(null);
  const [deleteModal, setDeleteModal] = useState<any>(null);
  const [selectedMedia, setSelectedMedia] = useState<number[]>([]);
  const [scheduleStart, setScheduleStart] = useState(localDate());
  const [scheduleDays, setScheduleDays] = useState("7");
  const [scheduleIntervals, setScheduleIntervals] = useState("11:00-13:00");
  const [scheduleStrategy, setScheduleStrategy] = useState("sequential");
  const [scheduleRanges, setScheduleRanges] = useState<string[]>([
    "11:00-13:00",
  ]);
  const setCampaignOpen = (open: boolean) => {
    if (open) {
      const ranges = defaults.intervals || ["11:00-13:00"];
      const models = defaults.script_ids || [];
      const days = Number(defaults.days || 7);
      const start = localDate();
      setSetupAccounts([]);
      setSetupMedia([]);
      setSetupScripts(models);
      setScheduleStart(start);
      setScheduleRanges(ranges);
      setScheduleDays(String(days));
      setScheduleStrategy(defaults.strategy || "sequential");
      setCoverPath(defaults.cover_path || "");
      setCoverName(defaults.cover_path ? "Capa padrão selecionada" : "");
      setCaptionListId(defaults.caption_list_id || null);
      setCaptionText(defaults.caption_text || "");
      setCampaignName(defaultCampaignName(start, days, ranges));
      setCampaignDescription(
        "Usará automaticamente todas as contas saudáveis e aptas a publicar.",
      );
    }
    setCampaignOpenState(open);
  };
  const refresh = () => {
    api(`/dashboard?period=${homePeriod}`).then(setDashboard);
    api("/meta/accounts").then(setAccounts);
    api("/media?kind=original").then(setMedia);
    api("/campaigns").then(setCampaigns);
    api("/scripts").then(setScripts);
    api("/caption-lists").then(setCaptionLists);
    api("/campaign-defaults").then(setDefaults);
    api("/account-campaign-sync-settings")
      .then((result: any) => setAccountSyncDelay(result.delay_days))
      .catch(() => {});
    api("/scheduled-posts").then(setAgenda);
    api("/activity").then(setActivity);
    api("/activity/summary").then(setActivitySummary);
    api(`/insights/reels?period=${insightPeriod}`)
      .then(setInsights)
      .catch(() => {});
    api("/tunnel/status").then(setTunnel);
  };
  useEffect(refresh, []);
  useEffect(() => {
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    api("/auth/status")
      .then((result) => setAuthenticated(result.authenticated))
      .catch(() => setAuthenticated(false));
  }, []);
  useEffect(() => {
    api(`/insights/reels?period=${insightPeriod}`)
      .then(setInsights)
      .catch(() => {});
  }, [insightPeriod]);
  useEffect(() => {
    if (page !== "Início") return;
    // Um período anterior pode responder depois do novo se a conexão oscilar.
    // Só aplicamos ao painel a resposta pertencente ao filtro atual.
    let cancelled = false;
    Promise.all([
      api(`/dashboard?period=${homePeriod}`),
      api(`/insights/reels?period=${homePeriod}`),
    ])
      .then(([nextDashboard, nextInsights]) => {
        if (cancelled) return;
        setDashboard(nextDashboard);
        setHomeInsights(nextInsights);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [page, homePeriod]);
  useEffect(() => {
    if (page !== "Início") return;
    api(`/insights/views-chart?period=${homePeriod}`)
      .then(setViewsChart)
      .catch(() => {});
  }, [page, homePeriod]);
  useEffect(() => {
    if (page !== "Insights") return;
    let cancelled = false;
    let timer: number | undefined;
    const finish = async () => {
      try {
        const data = await api(`/insights/reels?period=${insightPeriod}`);
        if (!cancelled) setInsights(data);
      } finally {
        if (!cancelled) setInsightsUpdating(false);
      }
    };
    const watch = async () => {
      try {
        const status = await api("/insights/status");
        if (cancelled) return;
        if (status.updating) {
          timer = window.setTimeout(watch, 1500);
          return;
        }
        await finish();
      } catch {
        if (!cancelled) setInsightsUpdating(false);
      }
    };
    (async () => {
      setInsightsUpdating(true);
      try {
        await api("/insights/sync", { method: "POST" });
        await watch();
      } catch {
        if (!cancelled) setInsightsUpdating(false);
      }
    })();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [page]);
  useEffect(() => {
    if (page !== "Contas") return;
    // A lista nunca depende só do estado antigo salvo no navegador: ela pede
    // uma validação real à Meta sempre que esta tela é aberta.
    api("/meta/accounts/refresh-health", { method: "POST" })
      .then(() => api("/meta/accounts"))
      .then(setAccounts)
      .catch(() => {});
  }, [page]);
  useEffect(() => {
    if (campaignOpen)
      setCampaignName(
        defaultCampaignName(
          scheduleStart,
          Number(scheduleDays) || 1,
          scheduleRanges,
        ),
      );
  }, [campaignOpen, scheduleStart, scheduleDays, scheduleRanges]);
  const importMedia = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!event.target.files?.length) return;
    const data = new FormData();
    [...event.target.files].forEach((file) => data.append("files", file));
    try {
      await api("/media/import", { method: "POST", body: data });
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const importScript = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const data = new FormData();
    data.append("file", file);
    try {
      const result = await api("/scripts/import", {
        method: "POST",
        body: data,
      });
      setSetupScripts((items) => [...items, result.id]);
      api("/scripts").then(setScripts);
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const importCover = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const data = new FormData();
    data.append("file", file);
    try {
      const result = await api("/campaign-covers/import", {
        method: "POST",
        body: data,
      });
      setCoverPath(result.path);
      setCoverName(result.name);
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const importDefaultCover = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const data = new FormData();
    data.append("file", file);
    try {
      const result = await api("/campaign-covers/import", {
        method: "POST",
        body: data,
      });
      setDefaults((current: any) => ({
        ...current,
        cover_path: result.path,
        cover_name: result.name,
      }));
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const importCaptions = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const data = new FormData();
    data.append("file", file);
    try {
      const result = await api("/caption-lists/import", {
        method: "POST",
        body: data,
      });
      setCaptionListId(result.id);
      api("/caption-lists").then(setCaptionLists);
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const createCampaign = async (event: FormEvent) => {
    event.preventDefault();
    const name = campaignName.trim();
    if (creating) return;
    if (
      !name ||
      !setupMedia.length ||
      !setupScripts.length ||
      !scheduleRanges.length
    ) {
      setNotice(
        "Preencha o nome e selecione mídias, scripts e ao menos um intervalo.",
      );
      return;
    }
    setCreating(true);
    setCampaignOpen(false);
    setNotice("Campanha criada. Processando vídeos e preparando agenda...");
    try {
      const created = await api("/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: campaignDescription.trim(),
          timezone: "America/Sao_Paulo",
        }),
      });
      await api(`/campaigns/${created.id}/setup`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_ids: setupMedia,
          script_ids: setupScripts,
          start_date: scheduleStart,
          days: Number(scheduleDays),
          intervals: scheduleRanges,
          strategy: scheduleStrategy,
          cover_path: coverPath,
          caption_list_id: captionListId,
          caption_text: captionText,
        }),
      });
      const generated = await api(
        `/campaigns/${created.id}/generate-schedule`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            start_date: scheduleStart,
            days: Number(scheduleDays),
            intervals: scheduleRanges,
            strategy: scheduleStrategy,
          }),
        },
      );
      setCampaignOpen(false);
      setCampaignName("");
      setCampaignDescription("");
      setCaptionText("");
      setCaptionListId(null);
      setCoverPath("");
      setCoverName("");
      setSetupAccounts([]);
      setSetupMedia([]);
      setSetupScripts([]);
      setPage("Campanhas");
      setNotice(
        `Campanha criada. Processando em lotes e preparando até ${generated.count} posts; acompanhe o andamento em Campanhas.`,
      );
      refresh();
    } catch (error: any) {
      setNotice(`Não foi possível concluir a campanha: ${error.message}`);
    } finally {
      setCreating(false);
    }
  };
  const openSetup = (campaign: any) => {
    setSetupCampaign(campaign);
    setSetupAccounts(campaign.account_ids || []);
    setSetupMedia(campaign.source_ids || []);
    setSetupScripts(campaign.script_ids || []);
    setCoverPath(campaign.cover_path || "");
    setCoverName(campaign.cover_path ? "Capa selecionada" : "");
    setCaptionListId(campaign.caption_list_id || null);
    setCaptionText(campaign.caption_text || "");
    setScheduleStart(campaign.schedule?.start_date || localDate());
    setScheduleDays(String(campaign.schedule?.days || 7));
    setScheduleRanges(campaign.schedule?.intervals || ["11:00-13:00"]);
    setScheduleStrategy(campaign.schedule?.strategy || "sequential");
  };
  const toggle = (
    value: number,
    selected: number[],
    setSelected: (items: number[]) => void,
  ) =>
    setSelected(
      selected.includes(value)
        ? selected.filter((x) => x !== value)
        : [...selected, value],
    );
  const saveSetup = async (event: FormEvent) => {
    event.preventDefault();
    if (!setupCampaign) return;
    if (!setupMedia.length || !setupScripts.length || !scheduleRanges.length) {
      setNotice("Selecione mídias, scripts e ao menos um intervalo.");
      return;
    }
    try {
      const body = {
        start_date: scheduleStart,
        days: Number(scheduleDays),
        intervals: scheduleRanges,
        strategy: scheduleStrategy,
      };
      await api(`/campaigns/${setupCampaign.id}/setup`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_ids: setupMedia,
          script_ids: setupScripts,
          ...body,
          cover_path: coverPath,
          caption_list_id: captionListId,
          caption_text: captionText,
        }),
      });
      await api(`/campaigns/${setupCampaign.id}/generate-schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setSetupCampaign(null);
      setNotice(
        "Configuração salva. Processamento e agenda iniciados automaticamente.",
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const processCampaign = async (campaign: any) => {
    try {
      setNotice("Iniciando o processamento em lotes...");
      if (!campaign.schedule)
        throw new Error("A configuração de agendamento não foi encontrada.");
      const generated = await api(
        `/campaigns/${campaign.id}/generate-schedule`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(campaign.schedule),
        },
      );
      setNotice(
        `Processamento iniciado para até ${generated.count} posts. Você pode fechar o navegador.`,
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const removeCampaign = async () => {
    if (!deleteModal) return;
    try {
      const action = deleteModal.action;
      if (action === "account")
        await api(`/meta/accounts/${deleteModal.id}`, { method: "DELETE" });
      else if (action === "script")
        await api(`/scripts/${deleteModal.id}`, { method: "DELETE" });
      else if (action === "captions")
        await api(`/caption-lists/${deleteModal.id}`, { method: "DELETE" });
      else if (action === "media")
        await api(`/media/${deleteModal.id}`, { method: "DELETE" });
      else if (action === "history")
        await api("/activity", { method: "DELETE" });
      else {
        const cancel = action === "cancel";
        await api(`/campaigns/${deleteModal.id}${cancel ? "/cancel" : ""}`, {
          method: cancel ? "POST" : "DELETE",
        });
      }
      setDeleteModal(null);
      setNotice(
        action === "history"
          ? "Histórico limpo."
          : action === "account"
            ? "Conta removida."
            : action === "script"
              ? "Script excluído."
              : action === "captions"
                ? "Lista excluída."
                : action === "media"
                  ? "Mídia excluída."
                  : action === "cancel"
                    ? "Campanha cancelada e agendamentos interrompidos."
                    : "Campanha excluída.",
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const removeMedia = (item: any) =>
    setDeleteModal({ ...item, action: "media" });
  const removeSelectedMedia = async () => {
    if (!deleteModal?.ids?.length) return;
    try {
      const result = await api("/media", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(deleteModal.ids),
      });
      setDeleteModal(null);
      setSelectedMedia([]);
      setNotice(
        `${result.deleted.length} mídia(s) excluída(s).${result.skipped.length ? ` ${result.skipped.length} protegida(s) foram mantidas.` : ""}`,
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const removeAccount = (account: any) =>
    setDeleteModal({
      ...account,
      action: "account",
      nome: `@${account.username || account.nome}`,
    });
  const openAccountReels = (targets: any[]) => {
    let opened = 0;
    targets.forEach((account) => {
      const username = (account.username || account.nome || "").replace(
        /^@/,
        "",
      );
      if (!username) return;
      // Abrir primeiro uma aba vazia é tratado como ação direta do clique pelo
      // navegador. Só depois ela é direcionada ao Instagram.
      const tab = window.open("", `instagram_reels_${account.id}`);
      if (!tab) return;
      opened += 1;
      tab.opener = null;
      tab.location.replace(`https://instagram.com/${username}/reels`);
    });
    if (opened < targets.length)
      setNotice(
        `O navegador bloqueou ${targets.length - opened} aba(s). Permita pop-ups para este site e tente novamente.`,
      );
    else if (targets.length > 1)
      setNotice(`${opened} contas aptas: uma aba foi aberta para cada conta.`);
  };
  const directInstagramConnectionUrl = `${window.location.origin}/api/meta/connect`;
  const copyInstagramConnectionLink = async () => {
    try {
      await navigator.clipboard.writeText(directInstagramConnectionUrl);
      setNotice(
        "Link direto de conexão copiado. Cole-o no navegador para conectar a conta.",
      );
    } catch (error: any) {
      setNotice(`Não foi possível copiar o link: ${error.message}`);
    }
  };
  const removeSelectedAccounts = async () => {
    if (!deleteModal?.ids?.length) return;
    try {
      const result = await api("/meta/accounts", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(deleteModal.ids),
      });
      setDeleteModal(null);
      setNotice(`${result.removed.length} conta(s) removida(s).`);
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const removeScript = (script: any) =>
    setDeleteModal({ ...script, action: "script" });
  const removeCaptionList = (list: any) =>
    setDeleteModal({ ...list, action: "captions" });
  const clearHistory = () =>
    setDeleteModal({ action: "history", nome: "todo o histórico" });
  const openNewCampaign = () => {
    setSetupAccounts([]);
    setSetupMedia([]);
    setSetupScripts(defaults.script_ids || []);
    setScheduleRanges(defaults.intervals || ["11:00-13:00"]);
    setScheduleDays(String(defaults.days || 7));
    setScheduleStrategy(defaults.strategy || "sequential");
    setCoverPath(defaults.cover_path || "");
    setCoverName(defaults.cover_path ? "Capa padrão selecionada" : "");
    setCaptionListId(defaults.caption_list_id || null);
    setCaptionText(defaults.caption_text || "");
    setCampaignOpen(true);
  };
  const saveDefaults = async () => {
    try {
      const payload = {
        intervals: (defaults.intervals || [])
          .map((value: string) => value.trim())
          .filter(Boolean),
        days: Number(defaults.days || 7),
        strategy: defaults.strategy || "sequential",
        script_ids: defaults.script_ids || [],
        cover_path: defaults.cover_path || "",
        caption_list_id: defaults.caption_list_id || null,
        caption_text: defaults.caption_text || "",
      };
      if (!payload.intervals.length)
        throw new Error("Informe ao menos um intervalo padrão.");
      const saved = await api("/campaign-defaults", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setDefaults(saved);
      setNotice("Padrões da campanha salvos.");
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const saveAccountSyncDelay = async () => {
    try {
      const delay_days = Math.max(
        0,
        Math.min(365, Number(accountSyncDelay) || 0),
      );
      const saved = await api("/account-campaign-sync-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delay_days }),
      });
      setAccountSyncDelay(saved.delay_days);
      setNotice("Prazo para entrada automática de contas salvo.");
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const saveInsightSettings = async (values: any) => {
    try {
      const result = await api("/insights/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      setNotice("Configuração dos Reels vencedores salva.");
      api(`/insights/reels?period=${homePeriod}`).then(setHomeInsights);
      return result;
    } catch (error: any) {
      setNotice(error.message);
      throw error;
    }
  };
  const scheduleCampaign = async (event: FormEvent) => {
    event.preventDefault();
    if (!scheduleModal) return;
    try {
      const result = await api(
        `/campaigns/${scheduleModal.id}/generate-schedule`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            start_date: scheduleStart,
            days: Number(scheduleDays),
            intervals: scheduleIntervals
              .split(",")
              .map((x) => x.trim())
              .filter(Boolean),
            strategy: scheduleStrategy,
          }),
        },
      );
      setScheduleModal(null);
      setNotice(
        `${result.count} publicações agendadas com mídias processadas.`,
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const generateSavedSchedule = async (campaign: any) => {
    if (!campaign.schedule) {
      setNotice("Edite a campanha e configure o agendamento.");
      return;
    }
    try {
      const result = await api(`/campaigns/${campaign.id}/generate-schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(campaign.schedule),
      });
      setNotice(
        `${result.count} publicações agendadas. Cada intervalo gerou um post por dia e por conta.`,
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const retryNow = async (post: any) => {
    try {
      await api(`/scheduled-posts/${post.id}/retry-now`, { method: "POST" });
      setNotice(
        "Nova tentativa iniciada. O status será atualizado em alguns segundos.",
      );
      refresh();
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  const login = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      setAuthenticated(true);
    } catch (error: any) {
      setNotice(error.message);
    }
  };
  if (authenticated === null) return null;
  if (!authenticated)
    return (
      <div className="login-page">
        <form className="modal" onSubmit={login}>
          <h1>Reels Manager</h1>
          <p>Entre para acessar seu painel.</p>
          {notice && <div className="notice">{notice}</div>}
          <label>
            E-mail
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <div className="modal-actions">
            <button className="primary" type="submit">
              Entrar
            </button>
          </div>
        </form>
      </div>
    );
  if (scheduleModal)
    return (
      <ScheduleDialog
        campaign={scheduleModal}
        start={scheduleStart}
        days={scheduleDays}
        intervals={scheduleIntervals}
        strategy={scheduleStrategy}
        setStart={setScheduleStart}
        setDays={setScheduleDays}
        setIntervals={setScheduleIntervals}
        setStrategy={setScheduleStrategy}
        cancel={() => setScheduleModal(null)}
        submit={scheduleCampaign}
      />
    );
  if (deleteModal?.action === "media-bulk")
    return (
      <BulkDeleteDialog
        count={deleteModal.ids.length}
        cancel={() => setDeleteModal(null)}
        confirm={removeSelectedMedia}
      />
    );
  if (deleteModal?.action === "account-bulk")
    return (
      <BulkAccountDeleteDialog
        count={deleteModal.ids.length}
        cancel={() => setDeleteModal(null)}
        confirm={removeSelectedAccounts}
      />
    );
  if (deleteModal)
    return (
      <DeleteDialog
        campaign={deleteModal}
        cancel={() => setDeleteModal(null)}
        confirm={removeCampaign}
      />
    );
  return (
    <main>
      <aside>
        <div className="brand">
          <div className="brandmark">R</div>
          <span>
            Reels <b>Manager</b>
          </span>
        </div>
        <nav>
          {pages.map(([label, Icon]) => (
            <button
              key={label}
              className={page === label ? "selected" : ""}
              onClick={() => setPage(label)}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <div className="aside-foot">
          <p>
            <i className="on" /> Scheduler ativo
          </p>
          <p>
            <i className="on" /> Meta configurada
          </p>
          <p>
            <i className={tunnel.active ? "on" : "off"} />{" "}
            {tunnel.active ? "Cloudflare pronto" : "Cloudflare iniciando"}
          </p>
          {tunnel.error && <p className="tunnel-error">{tunnel.error}</p>}
          <p>{dashboard.pendentes ?? 0} tarefas pendentes</p>
          <p>v0.1.0 local</p>
        </div>
      </aside>
      <section className="content">
        <header>
          <div>
            <h1>{page}</h1>
            <p>Gerencie as suas automações locais.</p>
          </div>
          <button className="primary" onClick={openNewCampaign}>
            <Plus size={18} /> Criar campanha
          </button>
        </header>
        {notice && (
          <div className="notice">
            {notice}
            <button aria-label="Fechar aviso" onClick={() => setNotice("")}>
              ×
            </button>
          </div>
        )}
        {page === "Início" && (
          <DashboardHome
            dashboard={dashboard}
            period={homePeriod}
            setPeriod={setHomePeriod}
            insights={homeInsights}
            chart={viewsChart}
            agenda={agenda}
            agendaMonth={agendaMonth}
            setAgendaMonth={setAgendaMonth}
            agendaDay={agendaDay}
            setAgendaDay={setAgendaDay}
            retryNow={retryNow}
            saveSettings={saveInsightSettings}
          />
        )}
        {page === "Contas" && (
          <AccountsPage
            accounts={accounts}
            connectionUrl={directInstagramConnectionUrl}
            copyLink={copyInstagramConnectionLink}
            openReels={openAccountReels}
            remove={removeAccount}
            bulkRemove={(ids: number[]) =>
              setDeleteModal({ action: "account-bulk", ids })
            }
          />
        )}
        {page === "Biblioteca" && (
          <>
            <div className="toolbar library-toolbar">
              <label className="primary">
                <Upload size={17} /> Adicionar mídias
                <input
                  hidden
                  type="file"
                  accept=".mp4,.mov"
                  multiple
                  onChange={importMedia}
                />
              </label>
              <button
                className="secondary"
                onClick={() =>
                  setSelectedMedia(
                    selectedMedia.length === media.length
                      ? []
                      : media.map((item) => item.id),
                  )
                }
              >
                {selectedMedia.length === media.length
                  ? "Limpar seleção"
                  : "Selecionar todas"}
              </button>
              <button
                className="secondary"
                onClick={async () => {
                  try {
                    setNotice("Atualizando miniaturas...");
                    const result = await api("/media/refresh-thumbnails", {
                      method: "POST",
                    });
                    setNotice(`${result.generated} miniaturas atualizadas.`);
                    setMedia([]);
                    refresh();
                  } catch (error: any) {
                    setNotice(error.message);
                  }
                }}
              >
                Atualizar miniaturas
              </button>
              {selectedMedia.length > 0 && (
                <button
                  className="danger"
                  onClick={() =>
                    setDeleteModal({ action: "media-bulk", ids: selectedMedia })
                  }
                >
                  Excluir selecionadas ({selectedMedia.length})
                </button>
              )}
            </div>
            <p className="library-note">
              Mostrando seus vídeos originais. As cópias processadas são
              temporárias e ficam vinculadas apenas aos agendamentos.
            </p>
            <div className="media-grid">
              {media.map((item) => (
                <article
                  className={`card media ${selectedMedia.includes(item.id) ? "selected-media" : ""}`}
                  key={item.id}
                  onClick={() =>
                    setSelectedMedia((items) =>
                      items.includes(item.id)
                        ? items.filter((id) => id !== item.id)
                        : [...items, item.id],
                    )
                  }
                >
                  <div className="media-check">
                    <input
                      aria-label={`Selecionar ${item.nome}`}
                      type="checkbox"
                      checked={selectedMedia.includes(item.id)}
                      readOnly
                    />
                  </div>
                  <div className="thumb library-preview">
                    <video
                      src={`${apiBaseUrl}/api/media/${item.id}/stream`}
                      poster={
                        item.thumbnail_url
                          ? `${apiBaseUrl}${item.thumbnail_url}`
                          : undefined
                      }
                      controls
                      preload="metadata"
                      onClick={(event) => event.stopPropagation()}
                    />
                  </div>
                  <b>{item.nome}</b>
                  <small>Original · {item.status}</small>
                  <button
                    className="danger"
                    onClick={(event) => {
                      event.stopPropagation();
                      removeMedia(item);
                    }}
                  >
                    Excluir
                  </button>
                </article>
              ))}
            </div>
            {!media.length && <Empty text="Sua biblioteca está vazia." />}
          </>
        )}
        {page === "Campanhas" && (
          <div className="panel">
            <div className="toolbar">
              <button className="primary" onClick={() => setCampaignOpen(true)}>
                <Plus size={17} /> Nova campanha
              </button>
            </div>
            <h2>Campanhas</h2>
            {campaigns.length ? (
              campaigns.map((campaign) => (
                <div className="row campaign-row" key={campaign.id}>
                  <span>
                    <b>{campaign.nome}</b>
                    {campaign.status === "PROCESSING" ||
                    campaign.progress?.status === "RUNNING" ||
                    campaign.progress?.status === "FAILED" ? (
                      <CampaignProgress
                        progress={campaign.progress}
                        status={campaign.status}
                      />
                    ) : (
                      <small>
                        {campaign.status === "DRAFT"
                          ? "Preparando automaticamente"
                          : campaign.status === "READY_TO_SCHEDULE"
                            ? "Retomando a preparação automaticamente…"
                            : campaign.status === "ACTIVE"
                              ? "Ativa — publicará automaticamente"
                              : `Etapa atual: ${campaign.status}`}
                      </small>
                    )}
                  </span>
                  <span className="row-actions">
                    <span
                      className={`tag ${campaign.status === "PROCESSING_FAILED" ? "tag-error" : ""}`}
                    >
                      {campaign.status === "PROCESSING"
                        ? "EM ATIVIDADE"
                        : campaign.status === "ACTIVE"
                          ? "ATIVA"
                          : campaign.status === "PROCESSING_FAILED"
                            ? "FALHOU"
                            : campaign.status}
                    </span>
                    <button
                      className="secondary"
                      disabled={campaign.status === "PROCESSING"}
                      onClick={() => openSetup(campaign)}
                    >
                      Editar
                    </button>
                    {campaign.status !== "CANCELLED" && (
                      <button
                        className="secondary"
                        onClick={() =>
                          setDeleteModal({ ...campaign, action: "cancel" })
                        }
                      >
                        Cancelar
                      </button>
                    )}
                    <button
                      className="danger"
                      onClick={() =>
                        setDeleteModal({ ...campaign, action: "delete" })
                      }
                    >
                      Excluir
                    </button>
                  </span>
                </div>
              ))
            ) : (
              <Empty
                text="Crie uma campanha para começar o processamento e os agendamentos."
                action="Criar campanha"
                on={() => setCampaignOpen(true)}
              />
            )}
          </div>
        )}
        {page === "Configurações" && (
          <>
            <div className="panel defaults-panel">
              <div className="panel-heading">
                <div>
                  <h2>Entrada de contas em campanhas</h2>
                  <p>
                    Após conectar ou reconectar, a conta só entra uma vez nas
                    campanhas ativas depois deste prazo.
                  </p>
                </div>
              </div>
              <div className="defaults-grid">
                <label>
                  Prazo padrão (dias inteiros)
                  <input
                    type="number"
                    min="0"
                    max="365"
                    value={accountSyncDelay}
                    onChange={(e) =>
                      setAccountSyncDelay(Number(e.target.value))
                    }
                  />
                  <small>
                    0 adiciona assim que a conta for validada; 1, 2 ou 3
                    aguardam esse número de dias.
                  </small>
                </label>
              </div>
              <div className="modal-actions">
                <button
                  className="primary"
                  type="button"
                  onClick={saveAccountSyncDelay}
                >
                  Salvar prazo
                </button>
              </div>
            </div>
            <div className="panel defaults-panel">
              <div className="panel-heading">
                <div>
                  <h2>Padrões para novas campanhas</h2>
                  <p>Usados automaticamente ao criar uma campanha.</p>
                </div>
              </div>
              <div className="defaults-grid">
                <label>
                  Dias
                  <input
                    type="number"
                    min="1"
                    max="366"
                    value={defaults.days || 7}
                    onChange={(e) =>
                      setDefaults({ ...defaults, days: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  Seleção das mídias
                  <select
                    value={defaults.strategy || "sequential"}
                    onChange={(e) =>
                      setDefaults({ ...defaults, strategy: e.target.value })
                    }
                  >
                    <option value="sequential">Sequencial</option>
                    <option value="random">Aleatória</option>
                  </select>
                </label>
                <label className="full-width">
                  Intervalos padrão <small>separe por vírgula</small>
                  <input
                    value={(defaults.intervals || []).join(", ")}
                    placeholder="11:00-13:00, 18:00-21:00"
                    onChange={(e) =>
                      setDefaults({
                        ...defaults,
                        intervals: e.target.value
                          .split(",")
                          .map((x) => x.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <label>
                  Lista JSON padrão
                  <select
                    value={defaults.caption_list_id || ""}
                    onChange={(e) =>
                      setDefaults({
                        ...defaults,
                        caption_list_id: e.target.value
                          ? Number(e.target.value)
                          : null,
                      })
                    }
                  >
                    <option value="">Nenhuma</option>
                    {captionLists.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.nome}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="full-width">
                  Legenda padrão
                  <textarea
                    value={defaults.caption_text || ""}
                    onChange={(e) =>
                      setDefaults({ ...defaults, caption_text: e.target.value })
                    }
                    placeholder="Opcional"
                  />
                </label>
              </div>
              <div className="defaults-media">
                <div>
                  <b>Capa padrão</b>
                  <small>
                    {defaults.cover_name || "Nenhuma capa selecionada"}
                  </small>
                </div>
                <label className="secondary import-script">
                  Escolher capa
                  <input
                    hidden
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp"
                    onChange={importDefaultCover}
                  />
                </label>
                {defaults.cover_path && (
                  <button
                    type="button"
                    className="danger"
                    onClick={() =>
                      setDefaults({
                        ...defaults,
                        cover_path: "",
                        cover_name: "",
                      })
                    }
                  >
                    Remover
                  </button>
                )}
              </div>
              <div className="defaults-scripts">
                <div>
                  <b>Scripts padrão</b>
                  <small>Serão marcados ao criar a campanha.</small>
                </div>
                <div className="selection-list">
                  {scripts
                    .filter((x) => x.ativo)
                    .map((x) => (
                      <label className="check selectable" key={x.id}>
                        <input
                          type="checkbox"
                          checked={(defaults.script_ids || []).includes(x.id)}
                          onChange={() =>
                            setDefaults({
                              ...defaults,
                              script_ids: (defaults.script_ids || []).includes(
                                x.id,
                              )
                                ? defaults.script_ids.filter(
                                    (id: number) => id !== x.id,
                                  )
                                : [...(defaults.script_ids || []), x.id],
                            })
                          }
                        />
                        {x.nome}
                      </label>
                    ))}
                  {!scripts.filter((x) => x.ativo).length && (
                    <p>Nenhum script ativo.</p>
                  )}
                </div>
              </div>
              <div className="modal-actions">
                <button
                  className="primary"
                  type="button"
                  onClick={saveDefaults}
                >
                  Salvar padrões
                </button>
              </div>
            </div>
            <div className="panel">
              <div className="toolbar">
                <h2>Scripts de processamento</h2>
              </div>
              {scripts.length ? (
                scripts.map((script) => (
                  <button
                    type="button"
                    className="selectable-row"
                    key={script.id}
                    onClick={() => removeScript(script)}
                  >
                    <span>
                      <b>{script.nome}</b>
                      <small>Clique para excluir</small>
                    </span>
                    <span className="tag">
                      {script.ativo ? "Ativo" : "Inativo"}
                    </span>
                  </button>
                ))
              ) : (
                <p>Nenhum script importado.</p>
              )}
            </div>
            <div className="panel">
              <h2>Listas de legendas</h2>
              {captionLists.length ? (
                captionLists.map((list) => (
                  <button
                    type="button"
                    className="selectable-row"
                    key={list.id}
                    onClick={() => removeCaptionList(list)}
                  >
                    <span>
                      <b>{list.nome}</b>
                      <small>
                        {list.quantidade} legendas · clique para excluir
                      </small>
                    </span>
                  </button>
                ))
              ) : (
                <p>Nenhuma lista importada.</p>
              )}
            </div>
            <div className="panel">
              <h2>Histórico</h2>
              <p>
                Remove processamentos e posts finalizados. Agendamentos
                pendentes são preservados.
              </p>
              <button className="danger" onClick={clearHistory}>
                Limpar histórico
              </button>
            </div>
          </>
        )}
        {page === "Histórico" && (
          <>
            <div className="metrics activity-metrics">
              <Metric
                icon={Film}
                label="Vídeos processados"
                value={activitySummary.processed ?? 0}
              />
              <Metric
                icon={Play}
                label="Publicados"
                value={activitySummary.published ?? 0}
              />
              <Metric
                icon={Clock}
                label="Aguardando horário"
                value={activitySummary.pending ?? 0}
              />
              <Metric
                icon={X}
                label="Com falha"
                value={activitySummary.failed ?? 0}
              />
              <Metric
                icon={Settings}
                label="Processando agora"
                value={activitySummary.processing ?? 0}
              />
            </div>
            <div className="panel">
              <div className="toolbar">
                <h2>Atividade recente</h2>
                <button className="secondary" onClick={refresh}>
                  Atualizar
                </button>
              </div>
              {activity.length ? (
                activity.map((item) => (
                  <div className="activity-row" key={item.id}>
                    <div>
                      <b>
                        {item.title} ·{" "}
                        {new Date(item.when).toLocaleString("pt-BR")}
                      </b>
                      <small className="activity-title">
                        {item.campaign} · Agendado para:{" "}
                        {new Date(
                          item.scheduled_for || item.when,
                        ).toLocaleString("pt-BR")}
                      </small>
                      {item.detail && (
                        <details open={item.status === "FAILED"}>
                          <summary>Ver detalhes</summary>
                          <pre>{item.detail}</pre>
                        </details>
                      )}
                    </div>
                    <span className="tag">{statusLabel(item.status)}</span>
                  </div>
                ))
              ) : (
                <Empty text="Ainda não há posts para mostrar." />
              )}
            </div>
          </>
        )}
      </section>
      {campaignOpen && (
        <CampaignDialog
          title="Nova campanha"
          submitLabel="Criar campanha"
          submit={createCampaign}
          cancel={() => setCampaignOpen(false)}
          name={campaignName}
          setName={setCampaignName}
          description={campaignDescription}
          setDescription={setCampaignDescription}
          accounts={accounts}
          selectedAccounts={setupAccounts}
          setAccounts={setSetupAccounts}
          media={media}
          selectedMedia={setupMedia}
          setMedia={setSetupMedia}
          scripts={scripts}
          selectedScripts={setupScripts}
          setScripts={setSetupScripts}
          importScript={importScript}
          start={scheduleStart}
          setStart={setScheduleStart}
          days={scheduleDays}
          setDays={setScheduleDays}
          ranges={scheduleRanges}
          setRanges={setScheduleRanges}
          strategy={scheduleStrategy}
          setStrategy={setScheduleStrategy}
          coverPath={coverPath}
          coverName={coverName}
          importCover={importCover}
          clearCover={() => {
            setCoverPath("");
            setCoverName("");
          }}
          captionLists={captionLists}
          captionListId={captionListId}
          setCaptionListId={setCaptionListId}
          importCaptions={importCaptions}
          captionText={captionText}
          setCaptionText={setCaptionText}
        />
      )}
      {setupCampaign && (
        <CampaignDialog
          title={`Configurar: ${setupCampaign.nome}`}
          submitLabel="Salvar configuração"
          submit={saveSetup}
          cancel={() => setSetupCampaign(null)}
          accounts={accounts}
          selectedAccounts={setupAccounts}
          setAccounts={setSetupAccounts}
          media={media}
          selectedMedia={setupMedia}
          setMedia={setSetupMedia}
          scripts={scripts}
          selectedScripts={setupScripts}
          setScripts={setSetupScripts}
          importScript={importScript}
          start={scheduleStart}
          setStart={setScheduleStart}
          days={scheduleDays}
          setDays={setScheduleDays}
          ranges={scheduleRanges}
          setRanges={setScheduleRanges}
          strategy={scheduleStrategy}
          setStrategy={setScheduleStrategy}
          coverPath={coverPath}
          coverName={coverName}
          importCover={importCover}
          clearCover={() => {
            setCoverPath("");
            setCoverName("");
          }}
          captionLists={captionLists}
          captionListId={captionListId}
          setCaptionListId={setCaptionListId}
          importCaptions={importCaptions}
          captionText={captionText}
          setCaptionText={setCaptionText}
        />
      )}
    </main>
  );
}
function Metric({ icon: Icon, label, value }: any) {
  return (
    <div className="card metric">
      <div className="icon">
        <Icon size={19} />
      </div>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}
function ViewsChart({ points }: any) {
  const [hovered, setHovered] = useState<number | null>(null);
  const data = (points || []) as any[];
  const width = 720,
    height = 130,
    padding = 12,
    measured = data.filter((item) => item.views !== null && item.views !== undefined),
    max = Math.max(1, ...measured.map((item) => Number(item.views) || 0));
  const pointPositions = data.map((item, index) => {
    if (item.views === null || item.views === undefined) return null;
    return {
      x: padding + (data.length < 2 ? 0 : (index * (width - padding * 2)) / (data.length - 1)),
      y: height - padding - ((Number(item.views) || 0) / max) * (height - padding * 2),
    };
  });
  const segments: Array<Array<{ x: number; y: number }>> = [];
  let currentSegment: Array<{ x: number; y: number }> = [];
  pointPositions.forEach((point) => {
    if (point) currentSegment.push(point);
    else if (currentSegment.length) { segments.push(currentSegment); currentSegment = []; }
  });
  if (currentSegment.length) segments.push(currentSegment);
  const smoothPath = (segment: Array<{ x: number; y: number }>) => {
    if (segment.length < 2) return "";
    let path = `M ${segment[0].x} ${segment[0].y}`;
    for (let index = 1; index < segment.length - 1; index++) {
      const previous = segment[index];
      const next = segment[index + 1];
      path += ` Q ${previous.x} ${previous.y} ${(previous.x + next.x) / 2} ${(previous.y + next.y) / 2}`;
    }
    const last = segment[segment.length - 1];
    path += ` L ${last.x} ${last.y}`;
    return path;
  };
  const dateOf = (value: string) =>
    new Date(value.includes("T") ? value : `${value}T12:00:00`);
  const format = (value: string) =>
    dateOf(value).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: data.length === 24 ? "2-digit" : undefined,
      minute: data.length === 24 ? "2-digit" : undefined,
    });
  const hoverLabel = (item: any) =>
    `${item.label || dateOf(item.date).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: item.date.includes("T") ? "short" : undefined })} · ${Number(item.views || 0).toLocaleString("pt-BR")} novas views`;
  const hoveredPoint = hovered === null ? null : pointPositions[hovered];
  return (
    <div className="views-chart">
      {data.length ? (
        <>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Gráfico de views"
            onMouseLeave={() => setHovered(null)}
          >
            <line
              x1={padding}
              y1={height - padding}
              x2={width - padding}
              y2={height - padding}
            />
            {segments.map((segment, index) => <path className="views-chart-line" key={index} d={smoothPath(segment)} />)}
            {data.map((item, index) => {
              const point = pointPositions[index];
              return point ? <rect key={item.date} className="views-chart-hit" x={point.x-12} y={padding} width="24" height={height-padding*2} tabIndex={0} onMouseEnter={() => setHovered(index)} onFocus={() => setHovered(index)} /> : null;
            })}
            {hovered !== null && hoveredPoint && <g className="views-chart-tooltip" transform={`translate(${Math.max(8, Math.min(width - 214, hoveredPoint.x - 102))},${Math.max(4, hoveredPoint.y - 35)})`}><rect width="204" height="26" rx="6"/><text x="10" y="17">{hoverLabel(data[hovered])}</text></g>}
          </svg>
          <div className="views-chart-labels">
            <span>{data[0].label || format(data[0].date)}</span>
            <b>{max.toLocaleString("pt-BR")} novas views no pico</b>
            <span>{data[data.length - 1].label || format(data[data.length - 1].date)}</span>
          </div>
        </>
      ) : (
        <p>Nenhum Reel publicado neste intervalo.</p>
      )}
    </div>
  );
}
function DashboardHome({
  dashboard,
  period,
  setPeriod,
  insights,
  chart,
  agenda,
  agendaMonth,
  setAgendaMonth,
  agendaDay,
  setAgendaDay,
  retryNow,
  saveSettings,
}: any) {
  const reels = insights.reels || [];
  const reelsPreservados = insights.reels_preservados || [];
  const [limit, setLimit] = useState(20);
  const [minimumViews, setMinimumViews] = useState(0);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setLimit(insights.settings?.limit ?? 20);
    setMinimumViews(insights.settings?.minimum_views ?? 0);
  }, [insights.settings?.limit, insights.settings?.minimum_views]);
  const save = async () => {
    setSaving(true);
    try {
      await saveSettings({
        limit: Math.max(1, Number(limit) || 1),
        minimum_views: Math.max(0, Number(minimumViews) || 0),
      });
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <div className="home-periods">
        <span>Resumo:</span>
        {[
          ["total", "Total"],
          ["24h", "24h"],
          ["7d", "7 dias"],
          ["30d", "30 dias"],
        ].map(([value, label]) => (
          <button
            key={value}
            className={period === value ? "primary" : "secondary"}
            onClick={() => setPeriod(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="metrics dashboard-metrics">
        <Metric
          icon={Users}
          label="Contas ativas"
          value={dashboard.contas_aptas ?? 0}
        />
        <Metric
          icon={CalendarDays}
          label="Vídeos agendados"
          value={dashboard.agendados ?? 0}
        />
        <Metric
          icon={Clock}
          label="Processando"
          value={dashboard.pendentes ?? 0}
        />
        <Metric
          icon={CheckCircle2}
          label="Vídeos postados"
          value={dashboard.publicados ?? 0}
        />
      </div>
      <div className="panel dashboard-insights">
        <div className="panel-heading">
          <div>
            <h2>Insights</h2>
            <p>Novas views registradas em cada horário ou dia do intervalo.</p>
          </div>
        </div>
        <ViewsChart points={chart.points} />
        <div className="dashboard-insights-total">
          <span>
            <Eye size={16} />
            {(insights.summary?.views ?? 0).toLocaleString("pt-BR")} views
          </span>
          <span>
            <Heart size={16} />
            {(insights.summary?.likes ?? 0).toLocaleString("pt-BR")} curtidas
          </span>
          <span>
            <MessageCircle size={16} />
            {(insights.summary?.comments ?? 0).toLocaleString("pt-BR")}{" "}
            comentários
          </span>
        </div>
        <div className="dashboard-ranking-heading">
          <h2 className="dashboard-ranking-title">Reels com mais views</h2>
          <div className="insight-settings">
            <label>
              Mostrar até
              <input
                type="number"
                min="1"
                max="100"
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
              />
              <small>Reels vencedores</small>
            </label>
            <label>
              Mínimo de views
              <input
                type="number"
                min="0"
                value={minimumViews}
                onChange={(event) =>
                  setMinimumViews(Number(event.target.value))
                }
              />
              <small>para entrar no ranking</small>
            </label>
            <button className="secondary" disabled={saving} onClick={save}>
              {saving ? "Salvando..." : "Salvar ranking"}
            </button>
          </div>
        </div>
        {reels.length ? (
          <div className="dashboard-reels">
            {reels.map((reel: any, index: number) => {
              const video = reel.cached_video_url
                ? `${apiBaseUrl}${reel.cached_video_url}`
                : "";
              return (
                <article className="dashboard-reel" key={reel.id}>
                  {video ? (
                    <video
                      src={video}
                      controls
                      muted
                      preload="auto"
                    />
                  ) : (
                    <div className="insight-placeholder">
                      <Film size={22} /> Vídeo sendo preservado…
                    </div>
                  )}
                  <div>
                    <b>
                      #{index + 1} · @{reel.conta}
                    </b>
                    <strong>
                      {Number(reel.views || 0).toLocaleString("pt-BR")} views
                    </strong>
                    <small>
                      <Heart size={13} />
                      {reel.likes || 0} <MessageCircle size={13} />
                      {reel.comments || 0}
                    </small>
                    {reel.permalink ? (
                      <a
                        className="reel-link"
                        href={reel.permalink}
                        target="_blank"
                        rel="noreferrer"
                        title="Abrir Reel no Instagram"
                      >
                        <ArrowUpRight size={15} /> Abrir Reel
                      </a>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <Empty text="Nenhum Reel encontrado neste intervalo." />
        )}
        {reelsPreservados.length > 0 && (
          <details className="preserved-reels">
            <summary>
              Ver {reelsPreservados.length} Reel(is) preservado(s) de conta(s) que caíram
            </summary>
            <p>
              Eles continuam nos totais e nos insights, mesmo sem a conta estar apta para publicar.
            </p>
            <div className="dashboard-reels preserved-reels-grid">
              {reelsPreservados.map((reel: any) => {
                const video = reel.cached_video_url ? `${apiBaseUrl}${reel.cached_video_url}` : "";
                return (
                  <article className="dashboard-reel" key={`preserved-${reel.id}`}>
                    {video ? <video src={video} controls muted preload="metadata" /> : <div className="insight-placeholder"><Film size={22} /> Vídeo preservado sem cópia local</div>}
                    <div>
                      <b>@{reel.conta}</b>
                      <strong>{Number(reel.views || 0).toLocaleString("pt-BR")} views</strong>
                      <small><Heart size={13} /> {reel.likes || 0} <MessageCircle size={13} /> {reel.comments || 0}</small>
                    </div>
                  </article>
                );
              })}
            </div>
          </details>
        )}
      </div>
      <section className="dashboard-full-agenda">
        <div className="panel-heading">
          <div>
            <h2>Agenda</h2>
            <p>Calendário completo e horários de todas as contas aptas.</p>
          </div>
        </div>
        <AgendaCalendar
          agenda={agenda}
          month={agendaMonth}
          setMonth={setAgendaMonth}
          selectedDay={agendaDay}
          setSelectedDay={setAgendaDay}
          retryNow={retryNow}
        />
      </section>
    </>
  );
}
function CampaignProgress({ progress, status }: any) {
  const total = Number(progress?.total || 0);
  const completed = Number(progress?.completed || 0);
  const percent = total
    ? Math.min(100, Math.round((completed * 100) / total))
    : 0;
  return (
    <div className="campaign-progress">
      <small>
        <b>
          {progress?.message ||
            (status === "PROCESSING_FAILED"
              ? "A preparação falhou."
              : "Preparando processamento...")}
        </b>
      </small>
      {total > 0 && (
        <>
          <div className="progress-track">
            <i style={{ width: `${percent}%` }} />
          </div>
          <small>
            <b>
              {completed}/{total}
            </b>{" "}
            vídeos processados · {progress?.scheduled || 0} posts agendados
            {progress?.current_batch ? ` · lote ${progress.current_batch}` : ""}
          </small>
        </>
      )}
      {progress?.current_media && (
        <small>Arquivo atual: {progress.current_media}</small>
      )}
      {progress?.error && (
        <small className="progress-error">Erro: {progress.error}</small>
      )}
    </div>
  );
}
function Empty({
  text,
  action,
  on,
}: {
  text: string;
  action?: string;
  on?: () => void;
}) {
  return (
    <div className="empty">
      <Film size={34} />
      <p>{text}</p>
      {action && (
        <button className="secondary" onClick={on}>
          {action}
        </button>
      )}
    </div>
  );
}
function AgendaCalendar({
  agenda,
  month,
  setMonth,
  selectedDay,
  setSelectedDay,
  retryNow,
}: any) {
  const [accountFilters, setAccountFilters] = useState<string[]>([]);
  const [hourFilters, setHourFilters] = useState<number[]>([]);
  const monthStart = new Date(month.getFullYear(), month.getMonth(), 1);
  const monthEnd = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const monthLabel = monthStart.toLocaleDateString("pt-BR", {
    month: "long",
    year: "numeric",
  });
  const allPosts = agenda
    .map((post: any) => ({ ...post, date: new Date(post.quando) }))
    .filter(
      (post: any) =>
        post.conta_apta !== false && !Number.isNaN(post.date.getTime()),
    );
  const accountNames = [
    ...new Set(allPosts.map((post: any) => post.conta).filter(Boolean)),
  ].sort() as string[];
  const posts = allPosts.filter(
    (post: any) =>
      (!accountFilters.length || accountFilters.includes(post.conta)) &&
      (!hourFilters.length || hourFilters.includes(post.date.getHours())),
  );
  const toggleAccount = (name: string) =>
    setAccountFilters((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name],
    );
  const toggleHour = (hour: number) =>
    setHourFilters((current) =>
      current.includes(hour)
        ? current.filter((item) => item !== hour)
        : [...current, hour].sort((a, b) => a - b),
    );
  const countByDay = new Map<string, number>();
  posts.forEach((post: any) => {
    const key = agendaDateKey(post.date);
    countByDay.set(key, (countByDay.get(key) || 0) + 1);
  });
  const firstWeekday = (monthStart.getDay() + 6) % 7;
  const cells = Array.from(
    { length: firstWeekday + monthEnd.getDate() },
    (_, index) =>
      index < firstWeekday
        ? null
        : new Date(
            month.getFullYear(),
            month.getMonth(),
            index - firstWeekday + 1,
          ),
  );
  const selectedPosts = posts
    .filter((post: any) => agendaDateKey(post.date) === selectedDay)
    .sort((a: any, b: any) => a.date.getTime() - b.date.getTime());
  const hours = new Map<number, any[]>();
  selectedPosts.forEach((post: any) => {
    const hour = post.date.getHours();
    hours.set(hour, [...(hours.get(hour) || []), post]);
  });
  const selectedLabel = selectedDay
    ? new Date(`${selectedDay}T12:00:00`).toLocaleDateString("pt-BR", {
        weekday: "long",
        day: "2-digit",
        month: "long",
      })
    : "";
  const navigate = (offset: number) => {
    setMonth(new Date(month.getFullYear(), month.getMonth() + offset, 1));
    setSelectedDay("");
  };
  return (
    <>
      <div className="panel agenda-calendar-panel">
        <div className="agenda-calendar-header">
          <div>
            <h2>Calendário da agenda</h2>
            <p>Clique em um dia para ver os horários e posts programados.</p>
          </div>
          <div className="agenda-month-nav">
            <button
              className="icon-button"
              onClick={() => navigate(-1)}
              aria-label="Mês anterior"
            >
              <ChevronLeft size={20} />
            </button>
            <b>{monthLabel}</b>
            <button
              className="icon-button"
              onClick={() => navigate(1)}
              aria-label="Próximo mês"
            >
              <ChevronRight size={20} />
            </button>
          </div>
        </div>
        <div className="agenda-filters">
          <details className="agenda-filter-menu">
            <summary>
              Contas
              {accountFilters.length
                ? ` · ${accountFilters.length}`
                : " · todas"}
            </summary>
            <div className="agenda-filter-options">
              {accountNames.map((name) => (
                <label key={name}>
                  <input
                    type="checkbox"
                    checked={accountFilters.includes(name)}
                    onChange={() => toggleAccount(name)}
                  />
                  <span>@{name}</span>
                </label>
              ))}
              {accountFilters.length > 0 && (
                <button
                  className="link-button"
                  onClick={() => setAccountFilters([])}
                >
                  Limpar seleção
                </button>
              )}
            </div>
          </details>
          <details className="agenda-filter-menu">
            <summary>
              Horários
              {hourFilters.length ? ` · ${hourFilters.length}` : " · todos"}
            </summary>
            <div className="agenda-filter-options agenda-hour-options">
              {Array.from({ length: 24 }, (_, hour) => (
                <label key={hour}>
                  <input
                    type="checkbox"
                    checked={hourFilters.includes(hour)}
                    onChange={() => toggleHour(hour)}
                  />
                  <span>{String(hour).padStart(2, "0")}:00</span>
                </label>
              ))}
              {hourFilters.length > 0 && (
                <button
                  className="link-button"
                  onClick={() => setHourFilters([])}
                >
                  Limpar seleção
                </button>
              )}
            </div>
          </details>
        </div>
        <div className="agenda-weekdays">
          {["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
        <div className="agenda-month-grid">
          {cells.map((day: Date | null, index: number) =>
            day ? (
              <button
                key={agendaDateKey(day)}
                className={`agenda-day ${agendaDateKey(day) === selectedDay ? "selected" : ""} ${agendaDateKey(day) === agendaDateKey(new Date()) ? "today" : ""}`}
                onClick={() => setSelectedDay(agendaDateKey(day))}
              >
                <span>{day.getDate()}</span>
                {countByDay.get(agendaDateKey(day)) ? (
                  <small>
                    {countByDay.get(agendaDateKey(day))} post
                    {countByDay.get(agendaDateKey(day)) === 1 ? "" : "s"}
                  </small>
                ) : null}
              </button>
            ) : (
              <span key={`blank-${index}`} className="agenda-day-blank" />
            ),
          )}
        </div>
      </div>
      <div className="panel agenda-timeline-panel">
        <div className="agenda-timeline-heading">
          <div>
            <h2>
              {selectedDay
                ? `Horários de ${selectedLabel}`
                : "Selecione um dia no calendário"}
            </h2>
            <p>
              {selectedDay
                ? `${selectedPosts.length} publicação(ões) distribuída(s) por horário.`
                : "A grade de horários aparecerá aqui."}
            </p>
          </div>
          {selectedDay && (
            <button className="secondary" onClick={() => setSelectedDay("")}>
              Limpar dia
            </button>
          )}
        </div>
        {selectedDay && selectedPosts.length === 0 && (
          <Empty text="Nenhuma publicação neste dia." />
        )}
        {selectedDay && selectedPosts.length > 0 && (
          <div className="agenda-hour-grid">
            {[...hours.entries()]
              .sort(([hourA], [hourB]) => hourA - hourB)
              .map(([hour, items]) => (
                <section className="agenda-hour" key={hour}>
                  <b className="agenda-hour-label">
                    {String(hour).padStart(2, "0")}:00
                  </b>
                  <div>
                    {items.map((item: any) => (
                      <article className="agenda-post-chip" key={item.id}>
                        <time>
                          {item.date.toLocaleTimeString("pt-BR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </time>
                        <span>
                          <b>@{item.conta}</b>
                          <small>
                            {item.campanha} · {item.midia}
                          </small>
                          {item.erro && (
                            <small className="error-detail">{item.erro}</small>
                          )}
                        </span>
                        <span
                          className={`tag ${item.status === "FAILED" ? "tag-error" : ""}`}
                        >
                          {statusLabel(item.status)}
                        </span>
                        {item.status === "FAILED" && (
                          <button
                            className="secondary"
                            onClick={() => retryNow(item)}
                          >
                            Tentar
                          </button>
                        )}
                      </article>
                    ))}
                  </div>
                </section>
              ))}
          </div>
        )}
      </div>
    </>
  );
}
function InsightsPage({
  insights,
  period,
  setPeriod,
  updating,
  saveSettings,
}: any) {
  const label =
    period === "total"
      ? "Todos os Reels monitorados"
      : period === "24h"
        ? "Reels publicados nas últimas 24h"
        : period === "7d"
          ? "Reels publicados nos últimos 7 dias"
          : "Reels publicados nos últimos 30 dias";
  const unavailable = (insights.accounts || []).filter(
    (account: any) => account.error,
  );
  const totals = insights.summary || {};
  const metricViews =
    period === "total" ? (totals.views ?? 0) : (totals.views ?? 0);
  const [limit, setLimit] = useState(20);
  const [minimumViews, setMinimumViews] = useState(0);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setLimit(insights.settings?.limit ?? 20);
    setMinimumViews(insights.settings?.minimum_views ?? 0);
  }, [insights.settings?.limit, insights.settings?.minimum_views]);
  const submitSettings = async () => {
    setSaving(true);
    try {
      await saveSettings({
        limit: Number(limit) || 1,
        minimum_views: Math.max(0, Number(minimumViews) || 0),
      });
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <div className="metrics insight-metrics">
        <Metric
          icon={Eye}
          label={
            period === "total" ? "Views totais" : "Views dos Reels no período"
          }
          value={metricViews.toLocaleString("pt-BR")}
        />
        <Metric
          icon={Heart}
          label={
            period === "total"
              ? "Curtidas totais"
              : "Curtidas dos Reels no período"
          }
          value={(totals.likes ?? 0).toLocaleString("pt-BR")}
        />
        <Metric
          icon={MessageCircle}
          label={
            period === "total"
              ? "Comentários totais"
              : "Comentários dos Reels no período"
          }
          value={(totals.comments ?? 0).toLocaleString("pt-BR")}
        />
        <Metric
          icon={Film}
          label={
            period === "total"
              ? "Reels monitorados"
              : "Reels publicados no período"
          }
          value={totals.reels ?? 0}
        />
      </div>
      <div className="panel">
        <div className="insights-toolbar">
          <div>
            <h2>Reels com mais views</h2>
            <p>
              {label}.{" "}
              {updating
                ? "Atualizando os dados de todas as contas…"
                : "Dados atualizados automaticamente ao abrir esta página."}
            </p>
          </div>
        </div>
        <div className="insight-periods">
          {[
            ["total", "Total"],
            ["24h", "24h"],
            ["7d", "7 dias"],
            ["30d", "30 dias"],
          ].map(([value, label]) => (
            <button
              key={value}
              className={period === value ? "primary" : "secondary"}
              onClick={() => setPeriod(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="insight-settings">
          <label>
            Mostrar até
            <input
              type="number"
              min="1"
              max="100"
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
            <small>Reels vencedores</small>
          </label>
          <label>
            Mínimo de views
            <input
              type="number"
              min="0"
              value={minimumViews}
              onChange={(event) => setMinimumViews(Number(event.target.value))}
            />
            <small>para entrar no ranking</small>
          </label>
          <button
            className="secondary"
            disabled={saving}
            onClick={submitSettings}
          >
            {saving ? "Salvando..." : "Salvar ranking"}
          </button>
        </div>
        {(insights.reels || []).length ? (
          <div className="insight-list">
            {insights.reels.map((reel: any, index: number) => {
              const local = reel.library_media;
              const poster =
                reel.cached_thumbnail_url ||
                reel.thumbnail_url ||
                (local ? `${apiBaseUrl}${local.thumbnail_url}` : "");
              const savedVideo = reel.cached_video_url
                ? `${apiBaseUrl}${reel.cached_video_url}`
                : "";
              return (
                <article className="insight-row" key={reel.id}>
                  {savedVideo ? (
                    <video
                      className="insight-saved-video"
                      src={savedVideo}
                      poster={
                        poster
                          ? poster.startsWith("/")
                            ? `${apiBaseUrl}${poster}`
                            : poster
                          : undefined
                      }
                      controls
                      muted
                      preload="metadata"
                    />
                  ) : poster ? (
                    <img
                      className="insight-cover insight-saved-cover"
                      src={
                        poster.startsWith("/")
                          ? `${apiBaseUrl}${poster}`
                          : poster
                      }
                      alt={`Visual salvo do Reel de @${reel.conta}`}
                    />
                  ) : (
                    <div className="insight-placeholder">
                      <Film size={20} />
                    </div>
                  )}
                  <div>
                    <b>
                      #{index + 1} · @{reel.conta}
                    </b>
                    {local && (
                      <small className="library-source">
                        Origem na Biblioteca · {local.name}
                      </small>
                    )}
                    <small>{reel.caption || "Sem legenda"}</small>
                    <strong>{reel.views} views</strong>
                    <span className="insight-values">
                      <span>
                        <Heart size={14} />
                        {reel.likes}
                      </span>
                      <span>
                        <MessageCircle size={14} />
                        {reel.comments}
                      </span>
                    </span>
                  </div>
                  {reel.permalink && (
                    <a
                      className="secondary"
                      href={reel.permalink}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Abrir Reel
                    </a>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <Empty text="Nenhum Reel atingiu o mínimo configurado neste período." />
        )}
      </div>
      {unavailable.length > 0 && (
        <div className="panel">
          <h2>Insights indisponíveis</h2>
          {unavailable.map((account: any) => (
            <div className="row" key={account.id}>
              <span>
                <b>@{account.username}</b>
                <small>{account.error}</small>
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
function AccountsPage({
  accounts,
  connectionUrl,
  copyLink,
  openReels,
  remove,
  bulkRemove,
}: any) {
  const active = accounts.filter((account: any) => account.apta);
  const inactive = accounts.filter((account: any) => !account.apta);
  const render = (account: any) => (
    <article className="account-choice" key={account.id}>
      <span>
        <b>@{account.username || account.nome}</b>
        <small>
          {account.verificada_em
            ? `Última verificação: ${eventDate(account.verificada_em)}`
            : "Ainda não validada"}
          {account.erro ? ` · ${account.erro}` : ""}
        </small>
      </span>
      <span className="row-actions">
        <span className={`tag ${account.apta ? "" : "tag-error"}`}>
          {account.apta ? "APTA A PUBLICAR" : account.status || "COM ERRO"}
        </span>
        {account.apta && (
          <button
            className="icon-button account-open"
            title={`Abrir @${account.username || account.nome} no Instagram`}
            aria-label={`Abrir @${account.username || account.nome} no Instagram`}
            onClick={() => openReels([account])}
          >
            <ArrowUpRight size={18} />
          </button>
        )}
        <button className="danger" onClick={() => remove(account)}>
          Excluir
        </button>
      </span>
    </article>
  );
  return (
    <div className="panel">
      <div className="oauth-link">
        <b>Link direto para conectar Instagram</b>
        <small>
          Abra ou copie este link. Ele vai direto para a autorização oficial,
          sem entrar no painel.
        </small>
        <div>
          <input
            readOnly
            value={connectionUrl}
            aria-label="Link direto para conectar Instagram"
            onFocus={(event) => event.currentTarget.select()}
          />
          <button className="primary" onClick={copyLink}>
            <Users size={17} /> Copiar link
          </button>
        </div>
      </div>
      <div className="toolbar account-toolbar">
        {active.length > 0 && (
          <button className="secondary" onClick={() => openReels(active)}>
            <ArrowUpRight size={17} /> Abrir todas as contas aptas (
            {active.length})
          </button>
        )}
      </div>
      <h2>Contas ativas</h2>
      {active.length ? (
        <div className="account-list">{active.map(render)}</div>
      ) : (
        <Empty text="Nenhuma conta está saudável e apta a publicar." />
      )}
      <div className="account-error-heading">
        <h2 className="account-section-title">
          Contas com erro ou desconectadas
        </h2>
        {inactive.length > 0 && (
          <button
            className="danger"
            onClick={() =>
              bulkRemove(inactive.map((account: any) => account.id))
            }
          >
            Apagar todas com erro ({inactive.length})
          </button>
        )}
      </div>
      {inactive.length ? (
        <div className="account-list">{inactive.map(render)}</div>
      ) : (
        <p className="muted">Nenhuma conta com erro.</p>
      )}
    </div>
  );
}
function CampaignDialog(p: any) {
  const toggleItem = (id: number, items: number[], setItems: any) =>
    setItems(
      items.includes(id) ? items.filter((x) => x !== id) : [...items, id],
    );
  const originals = p.media.filter((m: any) => m.tipo === "original");
  const updateRange = (i: number, value: string) =>
    p.setRanges(p.ranges.map((x: string, n: number) => (n === i ? value : x)));
  return (
    <div className="modal-backdrop">
      <form className="modal campaign-wide" onSubmit={p.submit}>
        <div className="modal-title">
          <h2>{p.title}</h2>
          <button type="button" className="icon-button" onClick={p.cancel}>
            <X size={19} />
          </button>
        </div>
        <p className="campaign-account-note">
          As contas são incluídas automaticamente: somente as saudáveis,
          validadas e aptas a publicar.
        </p>
        <div className="campaign-columns">
          <section>
            {p.setName && (
              <>
                <label>
                  Nome
                  <input
                    value={p.name}
                    onChange={(e: any) => p.setName(e.target.value)}
                  />
                </label>
                <label>
                  Descrição
                  <textarea
                    value={p.description}
                    onChange={(e: any) => p.setDescription(e.target.value)}
                  />
                </label>
              </>
            )}
            <label>Mídias originais</label>
            <button
              type="button"
              className="secondary"
              onClick={() => p.setMedia(originals.map((m: any) => m.id))}
            >
              Selecionar todas
            </button>
            <div className="selection-list">
              {originals.map((m: any) => (
                <label className="check" key={m.id}>
                  <input
                    type="checkbox"
                    checked={p.selectedMedia.includes(m.id)}
                    onChange={() =>
                      toggleItem(m.id, p.selectedMedia, p.setMedia)
                    }
                  />
                  {m.nome}
                </label>
              ))}
            </div>
          </section>
          <section>
            <label>Scripts — ordem de execução</label>
            {p.scripts
              .filter((s: any) => s.ativo)
              .map((s: any) => (
                <label className="check" key={s.id}>
                  <input
                    type="checkbox"
                    checked={p.selectedScripts.includes(s.id)}
                    onChange={() =>
                      p.setScripts((items: number[]) =>
                        items.includes(s.id)
                          ? items.filter((x) => x !== s.id)
                          : [...items, s.id],
                      )
                    }
                  />
                  {p.selectedScripts.includes(s.id)
                    ? `${p.selectedScripts.indexOf(s.id) + 1}. `
                    : ""}
                  {s.nome}
                </label>
              ))}
            <label className="secondary import-script">
              Importar .py
              <input
                hidden
                type="file"
                accept=".py"
                onChange={p.importScript}
              />
            </label>
            <h3>Capa e legenda</h3>
            <label className="secondary import-script">
              {p.coverName || "Selecionar capa (opcional)"}
              <input
                hidden
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                onChange={p.importCover}
              />
            </label>
            {p.coverPath && (
              <button type="button" className="danger" onClick={p.clearCover}>
                Remover capa
              </button>
            )}
            <label>
              Legenda única <small>tem prioridade sobre a lista JSON</small>
              <textarea
                value={p.captionText}
                onChange={(e: any) => p.setCaptionText(e.target.value)}
                placeholder="Opcional"
              />
            </label>
            <label>
              Lista JSON de legendas
              <select
                value={p.captionListId || ""}
                onChange={(e: any) =>
                  p.setCaptionListId(
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
              >
                <option value="">Nenhuma</option>
                {p.captionLists.map((item: any) => (
                  <option key={item.id} value={item.id}>
                    {item.nome} ({item.quantidade})
                  </option>
                ))}
              </select>
            </label>
            <label className="secondary import-script">
              Importar lista JSON
              <input
                hidden
                type="file"
                accept=".json,application/json"
                onChange={p.importCaptions}
              />
            </label>
            <h3>Agendamento</h3>
            <div className="schedule-grid">
              <label>
                Começar em
                <input
                  type="date"
                  value={p.start}
                  onChange={(e: any) => p.setStart(e.target.value)}
                />
              </label>
              <label>
                Quantidade de dias
                <input
                  type="number"
                  min="1"
                  max="366"
                  value={p.days}
                  onChange={(e: any) => p.setDays(e.target.value)}
                />
                <small className="campaign-end-date">
                  Dia final:{" "}
                  <b>{campaignEndDate(p.start, Number(p.days) || 1)}</b>
                </small>
              </label>
            </div>
            <label>
              Seleção das mídias
              <select
                value={p.strategy}
                onChange={(e: any) => p.setStrategy(e.target.value)}
              >
                <option value="sequential">
                  Sequencial — usa todas e repete
                </option>
                <option value="random">Aleatória</option>
              </select>
            </label>
            <label>
              Intervalos{" "}
              <small>
                cada intervalo equivale a um post por dia e por conta
              </small>
            </label>
            {p.ranges.map((range: string, i: number) => (
              <div className="range-row" key={i}>
                <input
                  value={range}
                  onChange={(e: any) => updateRange(i, e.target.value)}
                  placeholder="11:00-13:00"
                />
                <button
                  type="button"
                  className="danger"
                  onClick={() =>
                    p.setRanges(
                      p.ranges.filter((_: string, n: number) => n !== i),
                    )
                  }
                >
                  Remover
                </button>
              </div>
            ))}
            <button
              type="button"
              className="secondary"
              onClick={() => p.setRanges([...p.ranges, "18:00-21:00"])}
            >
              + Adicionar intervalo
            </button>
          </section>
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={p.cancel}>
            Cancelar
          </button>
          <button className="primary">{p.submitLabel}</button>
        </div>
      </form>
    </div>
  );
}
function ScheduleDialog({
  campaign,
  start,
  days,
  intervals,
  strategy,
  setStart,
  setDays,
  setIntervals,
  setStrategy,
  cancel,
  submit,
}: any) {
  return (
    <div className="login-page">
      <form className="modal wide" onSubmit={submit}>
        <div className="modal-title">
          <h2>Agendar: {campaign.nome}</h2>
          <button type="button" className="icon-button" onClick={cancel}>
            <X size={19} />
          </button>
        </div>
        <p>Somente vídeos já processados serão usados.</p>
        <div className="schedule-grid">
          <label>
            Começar em
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label>
            Quantidade de dias
            <input
              type="number"
              min="1"
              max="366"
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
          </label>
        </div>
        <label>
          Intervalos <small>Ex.: 11:00-13:00, 18:00-21:00</small>
          <input
            value={intervals}
            onChange={(e) => setIntervals(e.target.value)}
          />
        </label>
        <label>
          Escolha das mídias
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
          >
            <option value="sequential">Sequencial — usa todas e repete</option>
            <option value="random">Aleatória</option>
          </select>
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={cancel}>
            Cancelar
          </button>
          <button className="primary">Gerar agenda</button>
        </div>
      </form>
    </div>
  );
}
function DeleteDialog({ campaign, cancel, confirm }: any) {
  const action = campaign.action;
  const content =
    action === "history"
      ? [
          "Limpar histórico?",
          "Processamentos e posts finalizados serão removidos. Agendamentos pendentes serão preservados.",
          "Limpar",
        ]
      : action === "media"
        ? [
            "Excluir mídia?",
            "A mídia será removida do armazenamento. Mídias em campanhas ou posts pendentes são protegidas.",
            "Excluir",
          ]
        : action === "account"
          ? [
              "Remover conta?",
              "Os posts pendentes desta conta serão cancelados.",
              "Remover",
            ]
          : action === "script"
            ? [
                "Excluir script?",
                "Campanhas sem outro script serão pausadas.",
                "Excluir",
              ]
            : action === "captions"
              ? [
                  "Excluir lista de legendas?",
                  "Campanhas deixarão de usar esta lista.",
                  "Excluir",
                ]
              : action === "cancel"
                ? [
                    "Cancelar campanha?",
                    `“${campaign.nome}” será mantida no histórico, mas todos os agendamentos pendentes serão cancelados.`,
                    "Cancelar",
                  ]
                : [
                    "Excluir campanha?",
                    `“${campaign.nome}” e seus agendamentos serão removidos.`,
                    "Excluir",
                  ];
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>{content[0]}</h2>
        <p>{content[1]}</p>
        <div className="modal-actions">
          <button className="secondary" onClick={cancel}>
            Voltar
          </button>
          <button className="danger" onClick={confirm}>
            {content[2]}
          </button>
        </div>
      </div>
    </div>
  );
}
function BulkDeleteDialog({ count, cancel, confirm }: any) {
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Excluir mídias selecionadas?</h2>
        <p>
          {count} mídia(s) serão removidas. As que estiverem em campanhas ou
          posts pendentes continuarão protegidas.
        </p>
        <div className="modal-actions">
          <button className="secondary" onClick={cancel}>
            Voltar
          </button>
          <button className="danger" onClick={confirm}>
            Excluir selecionadas
          </button>
        </div>
      </div>
    </div>
  );
}
function BulkAccountDeleteDialog({ count, cancel, confirm }: any) {
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>Excluir contas selecionadas?</h2>
        <p>
          {count} conta(s) serão desconectadas. Posts pendentes dessas contas
          serão cancelados.
        </p>
        <div className="modal-actions">
          <button className="secondary" onClick={cancel}>
            Voltar
          </button>
          <button className="danger" onClick={confirm}>
            Excluir selecionadas
          </button>
        </div>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
