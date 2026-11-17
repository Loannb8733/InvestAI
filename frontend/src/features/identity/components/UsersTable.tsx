import { Shield, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/lib/utils'
import { roleLabel } from '../format'
import type { ManagedUser } from '../types'

interface UsersTableProps {
  users: ManagedUser[]
  onToggleActive: (user: ManagedUser) => void
  onDelete: (user: ManagedUser) => void
}

const COLUMNS = ['Utilisateur', 'Rôle', 'Statut', 'MFA', 'Créé le']

function UserRow({ user, onToggleActive, onDelete }: { user: ManagedUser } & Omit<UsersTableProps, 'users'>) {
  return (
    <tr className="border-b last:border-0 hover:bg-muted/50">
      <td className="py-3">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-sm font-medium text-primary">{user.email?.charAt(0).toUpperCase() ?? 'U'}</span>
          </div>
          <div>
            <p className="font-medium">
              {user.first_name || ''} {user.last_name || ''}
            </p>
            <p className="text-sm text-muted-foreground">{user.email}</p>
          </div>
        </div>
      </td>
      <td className="py-3">
        <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>{roleLabel(user.role)}</Badge>
      </td>
      <td className="py-3">
        <Badge variant={user.is_active ? 'default' : 'destructive'}>{user.is_active ? 'Actif' : 'Inactif'}</Badge>
      </td>
      <td className="py-3">
        {user.mfa_enabled ? <Shield className="h-4 w-4 text-gain" /> : <span className="text-sm text-muted-foreground">-</span>}
      </td>
      <td className="py-3 text-sm">{formatDateTime(user.created_at)}</td>
      <td className="py-3 text-right">
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => onToggleActive(user)}>
            {user.is_active ? 'Désactiver' : 'Activer'}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-destructive hover:text-destructive tap-target"
            onClick={() => onDelete(user)}
            aria-label="Supprimer l'utilisateur"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

export default function UsersTable({ users, onToggleActive, onDelete }: UsersTableProps) {
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle>Utilisateurs</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                {COLUMNS.map((column) => (
                  <th key={column} scope="col" className="text-left py-3 text-sm font-medium text-muted-foreground">
                    {column}
                  </th>
                ))}
                <th scope="col" className="text-right py-3 text-sm font-medium text-muted-foreground">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <UserRow key={user.id} user={user} onToggleActive={onToggleActive} onDelete={onDelete} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
