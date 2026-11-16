import RegisterBrandPanel from '@/features/identity/components/RegisterBrandPanel'
import RegisterForm from '@/features/identity/components/RegisterForm'

export default function RegisterPage() {
  return (
    <div className="min-h-screen flex">
      <RegisterForm />
      <RegisterBrandPanel />
    </div>
  )
}
