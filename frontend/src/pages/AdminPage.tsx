import { useState } from 'react'
import { Plus, Shield, ShieldCheck, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/components/ui/page-skeleton'
import QueryErrorState from '@/components/ui/query-error-state'
import SpotlightGroup from '@/components/ui/spotlight-group'
import StatCard from '@/components/ui/stat-card'
import CreateUserDialog from '@/features/identity/components/CreateUserDialog'
import DeleteUserDialog from '@/features/identity/components/DeleteUserDialog'
import UsersTable from '@/features/identity/components/UsersTable'
import { useUserMutations, useUsers } from '@/features/identity/hooks'
import type { ManagedUser } from '@/features/identity/types'

const fmtCount = (n: number) => Math.round(n).toString()

export default function AdminPage() {
  const [createOpen, setCreateOpen] = useState(false)
  const [created, setCreated] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<ManagedUser | null>(null)
  const users = useUsers()
  const { create, setActive, remove } = useUserMutations(() => {
    setCreateOpen(false)
    setCreated((n) => n + 1)
  })

  if (users.isLoading) {
    return <PageSkeleton titre="Administration" forme="table" action />
  }
  if (users.error) {
    return (
      <QueryErrorState error={users.error} onRetry={users.refetch} title="Impossible de charger l'administration" />
    )
  }

  const list = users.data ?? []
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-serif font-medium">Administration</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Nouvel utilisateur
        </Button>
      </div>
      <SpotlightGroup className="grid gap-4 md:grid-cols-3">
        <StatCard className="spot-card" label="Utilisateurs totaux" icon={Users} value={list.length} format={fmtCount} />
        <StatCard
          className="spot-card"
          label="Utilisateurs actifs"
          icon={ShieldCheck}
          value={list.filter((u) => u.is_active).length}
          format={fmtCount}
        />
        <StatCard
          className="spot-card"
          label="MFA activé"
          icon={Shield}
          value={list.filter((u) => u.mfa_enabled).length}
          format={fmtCount}
        />
      </SpotlightGroup>
      <UsersTable
        users={list}
        onToggleActive={(user) => setActive.mutate({ id: user.id, is_active: !user.is_active })}
        onDelete={setDeleteTarget}
      />
      <CreateUserDialog
        key={created}
        open={createOpen}
        pending={create.isPending}
        onOpenChange={setCreateOpen}
        onCreate={(body) => create.mutate(body)}
      />
      <DeleteUserDialog
        user={deleteTarget}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={(id) => {
          remove.mutate(id)
          setDeleteTarget(null)
        }}
      />
    </div>
  )
}
