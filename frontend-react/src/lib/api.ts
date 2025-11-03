import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Types
export interface ChatQueryRequest {
  query: string;
  session_id?: string;
  payer_name?: string;
  rule_type?: string;
  include_sources?: boolean;
}

export interface Source {
  rule_id: number;
  payer_name: string;
  rule_type: string;
  title?: string;
  content_excerpt?: string;
  effective_date?: string;
  source_url?: string;
  similarity_score?: number;
  combined_score?: number;
}

export interface ChatQueryResponse {
  response: string;
  sources: Source[];
  session_id: string;
  query_id: number;
  response_time_ms: number;
}

export interface Payer {
  id: number;
  name: string;
  website?: string;
  priority?: string;
  is_active: boolean;
  total_rules: number;
}

export interface Alert {
  id: number;
  title: string;
  message: string;
  alert_type: string;
  severity: string;
  is_read: boolean;
  created_at: string;
}

export interface Stats {
  total_payers: number;
  total_rules: number;
  unread_alerts: number;
  scrape_jobs_last_7_days: number;
  rules_by_type: Record<string, number>;
}

// API Functions
export const chatApi = {
  query: async (data: ChatQueryRequest): Promise<ChatQueryResponse> => {
    const response = await api.post('/chat/query', data);
    return response.data;
  },
  
  getHistory: async (sessionId: string) => {
    const response = await api.get(`/chat/history/${sessionId}`);
    return response.data;
  },
};

export const payersApi = {
  getAll: async (): Promise<Payer[]> => {
    const response = await api.get('/payers');
    return response.data;
  },
  
  getById: async (id: number) => {
    const response = await api.get(`/payers/${id}`);
    return response.data;
  },
};

export const alertsApi = {
  getAll: async (unreadOnly = false, limit = 10): Promise<Alert[]> => {
    const response = await api.get('/alerts', {
      params: { unread_only: unreadOnly, limit },
    });
    return response.data;
  },
};

export const statsApi = {
  get: async (): Promise<Stats> => {
    const response = await api.get('/stats');
    return response.data;
  },
};

export const healthApi = {
  check: async () => {
    const response = await api.get('/health');
    return response.data;
  },
};
