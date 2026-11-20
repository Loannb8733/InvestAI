export interface GuideLink {
  label: string
  href: string
}

export interface GuideStep {
  title: string
  details: string[]
  link?: GuideLink
  permissionsChecked?: string[]
  permissionsForbidden?: string[]
  keys?: { name: string; field: string }[]
  warning?: string
}

export interface ExchangeGuideData {
  id: string
  name: string
  readOnlyWarning: string
  steps: GuideStep[]
  notes?: string[]
}
