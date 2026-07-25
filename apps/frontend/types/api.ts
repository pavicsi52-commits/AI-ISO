/**
 * Standard API envelope types mirroring the backend response contract
 * defined in docs/006_API_Design_Master.md.txt. Every gateway/service
 * response uses one of these two shapes.
 */

export interface ApiResponseMeta {
  request_id: string;
  timestamp: string;
}

export interface ApiSuccessResponse<TData> {
  success: true;
  message: string;
  data: TData;
  meta: ApiResponseMeta;
}

export interface ApiErrorDetail {
  code: string;
  details: string[];
}

export interface ApiErrorResponse {
  success: false;
  message: string;
  error: ApiErrorDetail;
  meta: ApiResponseMeta;
}

export type ApiResponse<TData> = ApiSuccessResponse<TData> | ApiErrorResponse;
