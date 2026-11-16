import type { components, paths } from './schema'
import { http } from './http'

type Method = 'get' | 'post' | 'put' | 'patch' | 'delete'

type Routes = { [P in keyof paths as P extends `/api/v1${infer R}` ? R : never]: paths[P] }

type Operation<M extends Method, R extends keyof Routes> = Routes[R] extends { [K in M]: infer O } ? O : never

type RouteFor<M extends Method> = {
  [R in keyof Routes]: [Operation<M, R>] extends [never] ? never : R
}[keyof Routes]

type ParamsOf<O> = O extends { parameters: infer P } ? P : never

type PathOption<O> = ParamsOf<O> extends { path: infer P } ? { path: P } : { path?: never }

type QueryOption<O> =
  ParamsOf<O> extends { query: infer Q }
    ? { query: Q }
    : ParamsOf<O> extends { query?: infer Q }
      ? [NonNullable<Q>] extends [never]
        ? { query?: never }
        : { query?: Q }
      : { query?: never }

type BodyOption<O> = O extends { requestBody: { content: { 'application/json': infer B } } }
  ? { body: B }
  : O extends { requestBody?: { content: { 'application/json': infer B } } }
    ? { body?: B }
    : { body?: never }

type Options<O> = PathOption<O> & QueryOption<O> & BodyOption<O>

type Args<O> = object extends Options<O> ? [options?: Options<O>] : [options: Options<O>]

type Json<Response> = Response extends { content: { 'application/json': infer T } } ? T : undefined

export type ResponseOf<O> = O extends { responses: { 200: infer S } }
  ? Json<S>
  : O extends { responses: { 201: infer S } }
    ? Json<S>
    : undefined

export type Schema<Name extends keyof components['schemas']> = components['schemas'][Name]

type LooseOptions = { path?: Record<string, string | number>; query?: object; body?: unknown }

function fill(route: string, path: LooseOptions['path']): string {
  return route.replace(/\{(\w+)\}/g, (_, key: string) => encodeURIComponent(String(path?.[key])))
}

function verb<M extends Method>(method: M) {
  return async <R extends RouteFor<M>>(
    route: R,
    ...[options]: Args<Operation<M, R>>
  ): Promise<ResponseOf<Operation<M, R>>> => {
    const { path, query, body } = (options ?? {}) as LooseOptions
    const response = await http.request({ method, url: fill(route, path), params: query, data: body })
    return response.data
  }
}

export const apiClient = {
  get: verb('get'),
  post: verb('post'),
  put: verb('put'),
  patch: verb('patch'),
  delete: verb('delete'),
}
