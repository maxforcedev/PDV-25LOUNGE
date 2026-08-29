"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Building2, Camera, GitBranch, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Input, Spinner } from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { formatZipCode, lookupAddressByZipCode, ViaCepError, zipCodeDigits } from "@/lib/viacep";
import { useAuth } from "@/providers/auth-provider";
import type { UserProfilePayload } from "@/types";

const emptyForm: UserProfilePayload = {
  first_name: "", last_name: "", birth_date: "", cpf: "", zip_code: "",
  street: "", address_number: "", address_complement: "", neighborhood: "",
  city: "", state: "",
};

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState<UserProfilePayload>(emptyForm);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [removingPhoto, setRemovingPhoto] = useState(false);
  const [zipLoading, setZipLoading] = useState(false);
  const [zipError, setZipError] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!user) return;
    setForm({
      first_name: user.first_name, last_name: user.last_name,
      birth_date: user.birth_date || "", cpf: user.cpf || "",
      zip_code: formatZipCode(user.zip_code || ""), street: user.street || "",
      address_number: user.address_number || "", address_complement: user.address_complement || "",
      neighborhood: user.neighborhood || "", city: user.city || "", state: user.state || "",
    });
    if (!user.profile_photo_url) { setPhotoPreview(""); return; }
    let active = true;
    let objectUrl = "";
    http.download(user.profile_photo_url).then(({ blob }) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setPhotoPreview(objectUrl);
    }).catch(() => setPhotoPreview(""));
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [user]);

  useEffect(() => {
    if (photo) {
      const url = URL.createObjectURL(photo);
      setPhotoPreview(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [photo]);

  useEffect(() => {
    const zipCode = zipCodeDigits(form.zip_code);
    if (zipCode.length !== 8) { setZipError(""); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setZipLoading(true);
      lookupAddressByZipCode(zipCode, controller.signal).then((address) => {
        setForm((current) => ({ ...current, street: address.street || current.street,
          address_complement: address.complement || current.address_complement,
          neighborhood: address.neighborhood || current.neighborhood,
          city: address.city || current.city, state: address.state || current.state }));
        setZipError("");
      }).catch((caught) => {
        if (!controller.signal.aborted) setZipError(caught instanceof ViaCepError ? caught.message : "Não foi possível consultar o CEP.");
      }).finally(() => { if (!controller.signal.aborted) setZipLoading(false); });
    }, 450);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [form.zip_code]);

  function update(key: keyof UserProfilePayload, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function choosePhoto(file?: File) {
    if (!file) return;
    const allowed = ["image/png", "image/jpeg", "image/webp"];
    if (!allowed.includes(file.type) || file.size <= 0 || file.size > 5 * 1024 * 1024) {
      setFields((current) => ({ ...current, profile_photo: ["Envie PNG, JPG, JPEG ou WEBP de até 5 MB."] }));
      return;
    }
    setFields((current) => ({ ...current, profile_photo: [] }));
    setPhoto(file);
  }

  async function removePhoto() {
    setRemovingPhoto(true); setError("");
    try {
      await http.delete("auth/me/photo/");
      setPhoto(null); setPhotoPreview(""); await refreshUser();
      setSuccess("Foto removida com sucesso.");
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível remover a foto."); }
    finally { setRemovingPhoto(false); }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setFields({}); setError(""); setSuccess("");
    const body = new FormData();
    Object.entries(form).forEach(([key, value]) => body.append(key, key === "zip_code" ? zipCodeDigits(value) : value));
    if (photo) body.append("profile_photo", photo);
    try {
      await http.patch("auth/me/", body); setPhoto(null); await refreshUser();
      setSuccess("Seus dados foram atualizados com sucesso.");
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields); }
      else setError("Não foi possível atualizar seus dados.");
    } finally { setSaving(false); }
  }

  return <>
    <PageHeader title="Meu perfil" description="Mantenha seus dados pessoais e sua identificação atualizados." />
    <div className="grid gap-6 p-4 sm:p-6 lg:grid-cols-[1.2fr_0.8fr] lg:p-8">
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Informações pessoais</h2><p className="mt-1 text-[11px] text-muted">Todos os campos complementares são opcionais.</p></div><UserRound className="size-5 text-muted" /></div>
        <form onSubmit={submit}>
          <div className="space-y-6 p-5 sm:p-6">
            {error && <Alert message={error} />}{success && <Alert type="success" message={success} />}
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <div className="flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-full border border-subtle bg-surface-muted text-2xl font-bold text-primary">
                {photoPreview ? <Image src={photoPreview} alt="Foto de perfil" width={96} height={96} unoptimized className="size-full object-cover" /> : `${user?.first_name?.[0] || ""}${user?.last_name?.[0] || ""}` || "?"}
              </div>
              <div><strong className="text-sm">Foto de perfil</strong><p className="mt-1 text-xs text-muted">PNG, JPG ou WEBP, até 5 MB.</p>
                <div className="mt-3 flex flex-wrap gap-2"><label className="btn btn-secondary cursor-pointer"><Camera className="size-4" />{photoPreview ? "Substituir" : "Selecionar foto"}<input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => choosePhoto(event.target.files?.[0])} /></label>
                {photoPreview && <Button type="button" variant="secondary" loading={removingPhoto} onClick={() => void removePhoto()}><Trash2 className="size-4" />Remover</Button>}</div>
                {fieldError(fields, "profile_photo") && <p className="field-error">{fieldError(fields, "profile_photo")}</p>}</div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2"><Field label="Nome" error={fieldError(fields, "first_name")}><Input required value={form.first_name} onChange={(e) => update("first_name", e.target.value)} /></Field><Field label="Sobrenome" error={fieldError(fields, "last_name")}><Input required value={form.last_name} onChange={(e) => update("last_name", e.target.value)} /></Field><Field label="E-mail"><Input value={user?.email || ""} readOnly /></Field><Field label="Aniversário" optional><Input type="date" value={form.birth_date} onChange={(e) => update("birth_date", e.target.value)} /></Field><Field label="CPF" optional error={fieldError(fields, "cpf")}><Input inputMode="numeric" value={form.cpf} onChange={(e) => update("cpf", e.target.value)} placeholder="000.000.000-00" /></Field></div>
            <div className="border-t border-subtle pt-5"><h3 className="text-sm font-bold">Endereço</h3><p className="mt-1 text-xs text-muted">Informe o CEP para preencher o endereço automaticamente.</p></div>
            <div className="grid gap-4 sm:grid-cols-2"><Field label="CEP" optional error={fieldError(fields, "zip_code") || zipError}><Input value={form.zip_code} onChange={(e) => update("zip_code", formatZipCode(e.target.value))} />{zipLoading && <span className="mt-1 flex items-center gap-1 text-xs text-primary"><Spinner className="size-3" />Consultando CEP...</span>}</Field><Field label="Logradouro" optional><Input value={form.street} onChange={(e) => update("street", e.target.value)} /></Field><Field label="Número" optional><Input value={form.address_number} onChange={(e) => update("address_number", e.target.value)} /></Field><Field label="Complemento" optional><Input value={form.address_complement} onChange={(e) => update("address_complement", e.target.value)} /></Field><Field label="Bairro" optional><Input value={form.neighborhood} onChange={(e) => update("neighborhood", e.target.value)} /></Field><Field label="Cidade" optional><Input value={form.city} onChange={(e) => update("city", e.target.value)} /></Field><Field label="Estado" optional><Input maxLength={2} value={form.state} onChange={(e) => update("state", e.target.value.toUpperCase())} /></Field></div>
          </div><div className="flex justify-end border-t border-subtle px-5 py-4 sm:px-6"><Button type="submit" loading={saving}>Salvar alterações</Button></div>
        </form>
      </section>
      <section className="card self-start overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Empresas e filiais</h2><p className="mt-1 text-[11px] text-muted">Seus vínculos de acesso</p></div><Building2 className="size-5 text-muted" /></div>
        {user?.companies.length ? <div className="divide-y divide-subtle">{user.companies.map((company) => { const companyBranches = user.branches.filter((branch) => branch.company_id === company.id); return <article key={company.id} className="p-5"><div className="flex items-center justify-between"><h3 className="text-sm font-bold">{company.trade_name}</h3>{company.is_owner && <ShieldCheck className="size-4 text-primary" />}</div><div className="mt-3 space-y-2">{companyBranches.map((branch) => <div key={branch.id} className="flex items-center gap-2 rounded-lg border border-subtle p-3 text-xs"><GitBranch className="size-4 text-primary" /><span><strong className="block">{branch.name}</strong><small className="text-muted">{branch.access_profile?.name || "Sem perfil"}</small></span></div>)}</div></article>; })}</div> : <EmptyState title="Nenhuma empresa vinculada" description="Sua conta ainda não possui vínculos." />}
      </section>
    </div>
  </>;
}
