import { Link } from 'react-router-dom'
import { FileQuestion, Home } from 'lucide-react'
import { Button } from '@/components/ui/button'
import AuroraCanvas from '@/components/ui/aurora-canvas'

export default function NotFoundPage() {
  return (
    <div className="relative flex flex-col items-center justify-center min-h-screen overflow-hidden p-8 text-center bg-background">
      <AuroraCanvas className="opacity-40" />
      <div className="relative z-10 flex flex-col items-center">
        <FileQuestion className="h-24 w-24 text-muted-foreground mb-6" />
        <h1 className="text-6xl font-serif font-medium mb-2">404</h1>
        <h2 className="text-2xl font-semibold mb-4">Page introuvable</h2>
        <p className="text-muted-foreground mb-8 max-w-md">
          La page que vous recherchez n'existe pas ou a été déplacée.
        </p>
        <Link to="/">
          <Button>
            <Home className="h-4 w-4 mr-2" />
            Retour au tableau de bord
          </Button>
        </Link>
      </div>
    </div>
  )
}
