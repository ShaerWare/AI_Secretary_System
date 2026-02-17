export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'

export interface DemoRoute {
  method: HttpMethod | HttpMethod[]
  pattern: RegExp
  handler: (params: RouteParams) => unknown | Promise<unknown>
}

export interface RouteParams {
  url: string
  method: HttpMethod
  body: unknown
  matches: RegExpExecArray
  searchParams: URLSearchParams
}
