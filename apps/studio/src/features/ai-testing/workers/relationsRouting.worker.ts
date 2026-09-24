import { computeRelationsRoutes, type RelationsRouteGeometry } from '../utils/relationsRouting'

self.onmessage = (event: MessageEvent<RelationsRouteGeometry>) => {
  self.postMessage(computeRelationsRoutes(event.data))
}
