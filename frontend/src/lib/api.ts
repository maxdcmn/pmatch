const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

if (typeof window !== 'undefined') {
  console.log('API Base URL:', API_BASE_URL);
}

export interface Contact {
  email: string;
  name: string;
  institution?: string;
  country?: string;
  title?: string;
  research_area?: string;
  profile_url?: string;
  abstracts?: string[];
  similarity_score?: number;
}

export interface LLMRequest {
  message: string;
  user_id?: string;
}

export interface LLMResponse {
  message: string;
  response: string;
  success: boolean;
  contacts?: Contact[];
  metadata?: {
    tools_used?: string[];
    tool_results?: unknown[];
    user_context_loaded?: boolean;
    contact?: {
      text: string;
      email: string;
      subject: string;
    };
    timestamp?: string;
  };
}

export interface UploadResponse {
  filename: string;
  content_type: string;
  message: string;
  user_id: string;
}

export interface EmailGenerationRequest {
  user_id: string;
  contacts: Contact[];
  email_type?: string;
}

export interface EmailGenerationResponse {
  subject: string;
  body: string;
  personalization_notes: string[];
  success: boolean;
}

export interface ApiError {
  detail: string;
  status_code: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);

      if (!response.ok) {
        const errorData: ApiError = await response.json().catch(() => ({
          detail: `HTTP ${response.status}: ${response.statusText}`,
          status_code: response.status,
        }));
        throw new Error(errorData.detail);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(`API request failed: ${error.message}`);
      }
      throw new Error('API request failed: Unknown error');
    }
  }

  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'GET',
    });
  }

  async uploadFile<T>(endpoint: string, file: File): Promise<T> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request<T>(endpoint, {
      method: 'POST',
      body: formData,
      headers: {},
    });
  }
}

const apiClient = new ApiClient(API_BASE_URL);

export const api = {
  async chatWithLLM(message: string, user_id?: string): Promise<LLMResponse> {
    return apiClient.post<LLMResponse>('/api/llm-chat', { message, user_id });
  },

  async uploadPDF(file: File): Promise<UploadResponse> {
    return apiClient.uploadFile<UploadResponse>('/api/upload-pdf', file);
  },

  async generateEmail(request: EmailGenerationRequest): Promise<EmailGenerationResponse> {
    return apiClient.post<EmailGenerationResponse>('/api/generate-email', request);
  },

  async healthCheck(): Promise<{ status: string; version: string }> {
    return apiClient.get<{ status: string; version: string }>('/healthz');
  },
};

export default api;
