"use client";

import { useMemo, useState } from "react";
import {
  Banknote,
  BarChart3,
  Boxes,
  Building2,
  ChevronDown,
  CircleHelp,
  FileSearch,
  Package,
  Search,
  ShoppingCart,
  Users,
  X,
} from "lucide-react";

const categories = [
  { id: "all", label: "Todos", icon: CircleHelp },
  { id: "start", label: "Primeiros passos", icon: Building2 },
  { id: "sales", label: "PDV e vendas", icon: ShoppingCart },
  { id: "cash", label: "Caixa", icon: Banknote },
  { id: "stock", label: "Estoque", icon: Boxes },
  { id: "catalog", label: "Produtos e categorias", icon: Package },
  { id: "access", label: "Usuários e acessos", icon: Users },
  { id: "reports", label: "Relatórios", icon: BarChart3 },
  { id: "audit", label: "Auditoria", icon: FileSearch },
] as const;

type CategoryId = (typeof categories)[number]["id"];

type Article = {
  id: string;
  category: Exclude<CategoryId, "all">;
  title: string;
  description: string;
  time: string;
  tags: string[];
  steps: string[];
  note?: string;
};

const articles: Article[] = [
  {
    id: "primeiro-acesso",
    category: "start",
    title: "Primeiro acesso e contexto da operação",
    description: "Entenda como Company, filial atual e permissões determinam o que aparece no sistema.",
    time: "3 min",
    tags: ["empresa", "filial", "acesso"],
    steps: [
      "Entre com o e-mail e a senha do usuário habilitado para login.",
      "No topo do painel, confirme a empresa e a filial atuais antes de operar.",
      "Ao trocar de filial, o CORE PDV recalcula menus, ações e permissões disponíveis.",
      "Se uma tela não estiver disponível, confirme primeiro se o perfil possui a capacidade necessária naquele contexto.",
    ],
  },
  {
    id: "configurar-filial",
    category: "start",
    title: "Configurar uma filial para começar a operar",
    description: "Checklist rápido de preço, estoque, caixa, taxa e comissão antes da primeira venda.",
    time: "5 min",
    tags: ["filial", "configuração", "primeira venda"],
    steps: [
      "Revise os dados cadastrais e as configurações operacionais da filial.",
      "Configure taxa de serviço, comissão padrão e política de estoque negativo conforme a operação.",
      "Ative as formas de pagamento que poderão ser utilizadas no PDV.",
      "Cadastre ou revise produtos, preços e estoque da filial.",
      "Crie ao menos um caixa físico e confirme que os usuários corretos podem abri-lo e vender.",
    ],
  },
  {
    id: "abrir-caixa",
    category: "cash",
    title: "Abrir um caixa",
    description: "Inicie uma CashSession com o fundo correto e mantenha a operação vinculada à filial certa.",
    time: "2 min",
    tags: ["caixa", "abertura", "fundo"],
    steps: [
      "Acesse Operação de caixa ou use o atalho de abertura dentro do PDV quando nenhum caixa estiver aberto.",
      "Escolha o caixa físico disponível.",
      "Informe o valor inicial em dinheiro da gaveta.",
      "Confirme a abertura e verifique se a sessão aparece como aberta antes de iniciar vendas comerciais.",
    ],
  },
  {
    id: "finalizar-venda",
    category: "sales",
    title: "Realizar e finalizar uma venda",
    description: "Do carrinho ao pagamento, com atendente obrigatório e valores recalculados pelo backend.",
    time: "4 min",
    tags: ["pdv", "venda", "pagamento", "atendente"],
    steps: [
      "No PDV, adicione os produtos e ajuste as quantidades.",
      "Confirme o atendente responsável pela venda.",
      "Revise promoções e descontos; quando necessário, solicite autorização de um usuário elegível.",
      "Defina se a taxa de serviço será cobrada conforme as permissões disponíveis.",
      "Escolha uma ou mais formas de pagamento e confirme a finalização.",
      "O backend recalcula valores, valida caixa e estoque e registra a operação de forma transacional.",
    ],
  },
  {
    id: "pagamento-dinheiro",
    category: "sales",
    title: "Pagamento em dinheiro e troco",
    description: "Saiba a diferença entre valor recebido, valor aplicado e troco.",
    time: "2 min",
    tags: ["dinheiro", "troco", "pagamento"],
    steps: [
      "Informe apenas o valor entregue pelo cliente no campo Valor recebido.",
      "O sistema aplica à venda somente o saldo necessário.",
      "O troco é calculado pelo backend e não aumenta a receita nem o valor aplicado à venda.",
      "Em pagamento dividido, o dinheiro cobre apenas o saldo restante após os outros métodos.",
    ],
  },
  {
    id: "consumacao",
    category: "sales",
    title: "Aplicar consumação ou cortesia",
    description: "Use o mesmo pedido do PDV para registrar consumação gratuita ou parcialmente cobrada.",
    time: "3 min",
    tags: ["consumação", "cortesia", "beneficiário"],
    steps: [
      "Monte o pedido normalmente no PDV.",
      "Na etapa de fechamento, escolha Aplicar consumação.",
      "Selecione o beneficiário e informe o valor cobrado, que pode ser R$ 0,00.",
      "Se houver cobrança, registre o pagamento normalmente; se for gratuita, nenhum Payment é criado.",
      "O estoque é movimentado pelas mesmas regras de uma venda, mas a operação permanece separada do faturamento comercial.",
    ],
  },
  {
    id: "fechar-caixa",
    category: "cash",
    title: "Fechar o caixa e conferir a gaveta",
    description: "Compare esperado em dinheiro, valor informado e diferença sem misturar PIX ou cartão.",
    time: "4 min",
    tags: ["caixa", "fechamento", "diferença"],
    steps: [
      "Abra o resumo da sessão antes de fechar.",
      "Confira vendas, consumações cobradas, entradas, sangrias e recebimentos por forma.",
      "O Esperado em dinheiro considera somente valores que realmente alteram a gaveta física.",
      "Informe o valor contado na gaveta.",
      "O sistema registra esperado, informado e diferença como snapshot do fechamento.",
    ],
  },
  {
    id: "sangria",
    category: "cash",
    title: "Registrar uma sangria",
    description: "Classifique a retirada e, quando aplicável, vincule o beneficiário.",
    time: "2 min",
    tags: ["sangria", "beneficiário", "caixa"],
    steps: [
      "Dentro da sessão aberta, escolha Sangria.",
      "Informe o valor e a categoria da retirada.",
      "Selecione o beneficiário quando a natureza da sangria estiver ligada a uma pessoa cadastrada.",
      "Adicione uma observação quando ela ajudar a explicar a operação.",
      "Lembre-se: sangria não é automaticamente despesa do resultado; ela é primeiro um movimento operacional de caixa.",
    ],
  },
  {
    id: "cadastrar-produto",
    category: "catalog",
    title: "Cadastrar um produto",
    description: "Defina categoria, preço, custo, unidade e comportamento de estoque sem duplicar regras no frontend.",
    time: "4 min",
    tags: ["produto", "preço", "categoria"],
    steps: [
      "Escolha uma Category e informe os dados comerciais do produto.",
      "Se o código interno ficar vazio, o backend gera um código único para a Company.",
      "Defina se o produto é vendável e se deve aparecer como favorito no PDV.",
      "Escolha o comportamento de estoque: direto, sem estoque ou por componentes.",
      "Salve e revise o preço efetivo da filial caso exista override de preço.",
    ],
  },
  {
    id: "produto-composto",
    category: "catalog",
    title: "Criar um produto composto ou combo",
    description: "Monte combos de um nível e faça a baixa acontecer nos componentes físicos.",
    time: "5 min",
    tags: ["combo", "composição", "componentes"],
    steps: [
      "Cadastre primeiro os componentes físicos com comportamento de estoque direto.",
      "No produto pai, selecione o comportamento por componentes.",
      "Adicione cada componente e sua quantidade; unidades UN não aceitam fração.",
      "Use as sugestões de custo/preço quando forem úteis, sem sobrescrever valores manuais já definidos.",
      "Ao vender o combo, o produto pai não baixa saldo próprio; os componentes são os itens físicos consumidos.",
    ],
  },
  {
    id: "entrada-estoque",
    category: "stock",
    title: "Registrar entrada de estoque",
    description: "Faça uma entrada individual ou em grupo por categoria com histórico de saldo anterior e final.",
    time: "3 min",
    tags: ["estoque", "entrada", "movimentação"],
    steps: [
      "Acesse Estoque e escolha + Movimentação.",
      "Selecione Entrada, a natureza da operação e o produto ou grupo por Category.",
      "Informe somente quantidades realmente recebidas.",
      "Cada produto movimentado gera seu próprio StockMovement auditável.",
      "Entradas também podem recuperar saldos negativos existentes.",
    ],
  },
  {
    id: "estoque-negativo",
    category: "stock",
    title: "Entender e regularizar estoque negativo",
    description: "Saiba quando o saldo pode ficar negativo e como corrigir antes de desativar essa política.",
    time: "4 min",
    tags: ["estoque negativo", "regularização", "filial"],
    steps: [
      "A política de estoque negativo é configurada por filial e é desabilitada por padrão.",
      "Quando permitida, o saldo negativo permanece real e visível; ele não é mascarado como zero.",
      "Antes de desativar a política, regularize todos os produtos negativos.",
      "A regularização gera movimentação de ajuste com antes, diferença, depois e ator.",
    ],
  },
  {
    id: "criar-usuario",
    category: "access",
    title: "Criar um usuário com ou sem login",
    description: "Use o mesmo cadastro para operadores do sistema e pessoas que só precisam existir na operação.",
    time: "4 min",
    tags: ["usuário", "login", "equipe"],
    steps: [
      "Cadastre nome e classificação operacional do usuário.",
      "Se ele não precisar entrar no sistema, mantenha can_login desabilitado; o e-mail pode ser dispensado conforme o cadastro.",
      "Para usuários com login, informe e-mail válido, senha e vínculos ativos de Company/Branch.",
      "A classificação do usuário não concede permissões por si só.",
    ],
  },
  {
    id: "perfil-permissoes",
    category: "access",
    title: "Configurar perfil e permissões",
    description: "Controle capacidades por perfil sem depender do nome Administrador, Gerente ou Operador.",
    time: "5 min",
    tags: ["perfil", "permissão", "rbac"],
    steps: [
      "Acesse Perfis de acesso e selecione o perfil da Company.",
      "Revise a matriz por módulo e as ações especiais.",
      "Conceda somente as capacidades necessárias para aquela função.",
      "Associe o perfil operacional ao acesso do usuário na filial correta.",
      "O backend continua sendo a fonte de verdade da autorização.",
    ],
  },
  {
    id: "bloquear-permissao",
    category: "access",
    title: "Bloquear uma permissão para um usuário específico",
    description: "Crie uma exceção individual sem duplicar um perfil inteiro.",
    time: "3 min",
    tags: ["bloqueio", "permissão", "filial"],
    steps: [
      "Abra Bloqueios de acesso e escolha o usuário.",
      "Defina se o bloqueio vale para toda a empresa ou para uma filial específica.",
      "Selecione uma ou várias capacidades herdadas que devem ser bloqueadas.",
      "Aplique o bloqueio; ele prevalece sobre a permissão herdada naquele escopo.",
      "Ao revogar o bloqueio, a avaliação volta a seguir normalmente o perfil.",
    ],
  },
  {
    id: "recebimentos",
    category: "reports",
    title: "Conferir faturamento, taxa e recebimentos",
    description: "Use a reconciliação padrão do CORE PDV para entender por que faturamento e pagamentos podem ter valores diferentes.",
    time: "4 min",
    tags: ["relatório", "recebimentos", "taxa de serviço", "faturamento"],
    steps: [
      "Faturamento de vendas representa os produtos após promoções e descontos.",
      "Some a Consumação cobrada para chegar ao Faturamento efetivo.",
      "Some a Taxa de serviço para chegar ao Total recebido.",
      "O total por forma de pagamento deve reconciliar com o recebido do mesmo recorte.",
      "Comissão não reduz o valor recebido; ela aparece separadamente como custo operacional.",
    ],
    note: "Faturamento de vendas + Consumação cobrada = Faturamento efetivo; + Taxa = Total recebido.",
  },
  {
    id: "resultado",
    category: "reports",
    title: "Ler o Resultado estimado",
    description: "Entenda quais entradas e custos participam da visão gerencial sem confundir o relatório com uma DRE contábil.",
    time: "4 min",
    tags: ["resultado", "cmv", "comissão", "taxa"],
    steps: [
      "Faturamento de vendas + Consumação cobrada = Faturamento efetivo; + Taxa = Total recebido.",
      "O sistema deduz CMV histórico de vendas, custo histórico de consumação, comissão e custos operacionais configurados.",
      "Sangria só reduz o resultado quando estiver explicitamente classificada como movimento que afeta o resultado.",
      "O relatório é gerencial e estimado; não substitui uma DRE contábil oficial.",
    ],
  },
  {
    id: "filtro-periodo",
    category: "reports",
    title: "Usar filtros de data e hora",
    description: "Aplique recortes precisos, inclusive para operações que atravessam meia-noite.",
    time: "2 min",
    tags: ["filtro", "data", "hora", "relatório"],
    steps: [
      "Escolha data/hora inicial e data/hora final ou utilize um atalho de período.",
      "Ao aplicar, KPIs, gráficos, tabela e exportação devem usar o mesmo intervalo.",
      "Drill-downs preservam o período sempre que o destino suporta os mesmos filtros.",
      "Em relatório de caixa, uma sessão pode intersectar o período; o resumo do período continua limitado ao intervalo escolhido.",
    ],
  },
  {
    id: "auditoria",
    category: "audit",
    title: "Consultar a Auditoria",
    description: "Descubra quem alterou uma informação, em qual contexto e o que mudou.",
    time: "3 min",
    tags: ["auditoria", "histórico", "segurança"],
    steps: [
      "Acesse Auditoria e filtre por período, filial, ator, módulo ou ação.",
      "Leia o resumo humano da alteração e o De → Para quando aplicável.",
      "Abra Ver detalhes apenas quando precisar de metadados técnicos adicionais.",
      "AuditLog é append-only no fluxo operacional e não deve ser editado ou apagado pela interface.",
    ],
  },
  {
    id: "formas-pagamento",
    category: "start",
    title: "Ativar ou inativar formas de pagamento",
    description: "Controle quais meios podem ser utilizados em novas operações sem apagar histórico antigo.",
    time: "2 min",
    tags: ["pix", "cartão", "dinheiro", "pagamento"],
    steps: [
      "Acesse Formas de pagamento com um usuário autorizado.",
      "Ative ou inative Dinheiro, PIX, Crédito e Débito conforme a operação da Company.",
      "Métodos inativos deixam de aparecer em novas vendas, mas pagamentos históricos permanecem válidos.",
    ],
  },
];

export function HelpCenter() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<CategoryId>("all");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("pt-BR");
    return articles.filter((article) => {
      if (category !== "all" && article.category !== category) return false;
      if (!normalized) return true;
      const haystack = `${article.title} ${article.description} ${article.tags.join(" ")} ${article.steps.join(" ")}`.toLocaleLowerCase("pt-BR");
      return haystack.includes(normalized);
    });
  }, [category, query]);

  return (
    <>
      <div className="mx-auto max-w-4xl">
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Busque por caixa, estoque, venda, permissão, relatório..."
            className="h-13 w-full rounded-2xl border border-subtle bg-surface pl-11 pr-11 text-sm font-medium text-fg shadow-[0_12px_35px_rgba(15,23,42,0.06)] outline-none transition placeholder:text-muted focus:border-primary/40 focus:ring-4 focus:ring-primary/10"
            aria-label="Buscar na Central de Ajuda"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} className="absolute right-2 top-1/2 inline-flex size-9 -translate-y-1/2 items-center justify-center rounded-xl text-muted hover:bg-surface-muted hover:text-fg" aria-label="Limpar busca">
              <X className="size-4" />
            </button>
          )}
        </div>

        <div className="mt-5 flex gap-2 overflow-x-auto pb-2" aria-label="Categorias de ajuda">
          {categories.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setCategory(id)}
              aria-pressed={category === id}
              className={`inline-flex h-9 shrink-0 items-center gap-2 rounded-xl border px-3.5 text-[11px] font-bold transition ${category === id ? "border-primary bg-primary text-white shadow-sm shadow-primary/20" : "border-subtle bg-surface text-muted hover:border-primary/25 hover:text-fg"}`}
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-10 grid gap-4 lg:grid-cols-2">
        {filtered.map((article) => {
          const CategoryIcon = categories.find((item) => item.id === article.category)?.icon ?? CircleHelp;
          return (
            <details key={article.id} id={article.id} className="group scroll-mt-24 rounded-2xl border border-subtle bg-surface shadow-[0_8px_28px_rgba(15,23,42,0.035)] open:border-primary/25 open:shadow-[0_18px_45px_rgba(15,23,42,0.07)]">
              <summary className="flex list-none cursor-pointer items-start gap-4 p-5 sm:p-6 [&::-webkit-details-marker]:hidden">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-info-surface text-info-strong"><CategoryIcon className="size-4.5" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
                    <span>{categories.find((item) => item.id === article.category)?.label}</span>
                    <span>·</span>
                    <span>{article.time}</span>
                  </div>
                  <h2 className="mt-2 text-[15px] font-extrabold leading-6 tracking-tight text-fg">{article.title}</h2>
                  <p className="mt-1.5 text-[12px] leading-5 text-muted">{article.description}</p>
                </div>
                <ChevronDown className="mt-1 size-4 shrink-0 text-muted transition duration-200 group-open:rotate-180" />
              </summary>
              <div className="border-t border-subtle px-5 pb-6 pt-5 sm:px-6">
                {article.note && <div className="mb-5 rounded-xl border border-primary/15 bg-info-surface px-4 py-3 text-[12px] font-semibold leading-5 text-info-strong">{article.note}</div>}
                <ol className="space-y-3">
                  {article.steps.map((step, index) => (
                    <li key={step} className="grid grid-cols-[26px_1fr] gap-3 text-[12px] leading-5 text-muted">
                      <span className="flex size-6 items-center justify-center rounded-full bg-surface-muted text-[9px] font-black text-fg">{index + 1}</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </details>
          );
        })}
      </div>

      {!filtered.length && (
        <div className="mt-10 rounded-2xl border border-dashed border-subtle bg-surface px-6 py-14 text-center">
          <Search className="mx-auto size-6 text-muted" />
          <h2 className="mt-4 text-sm font-extrabold text-fg">Nenhum guia encontrado</h2>
          <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-muted">Tente outro termo ou escolha uma categoria diferente. A busca considera títulos, descrições, tags e passos dos guias.</p>
          <button type="button" onClick={() => { setQuery(""); setCategory("all"); }} className="mt-5 inline-flex h-9 items-center justify-center rounded-xl border border-subtle bg-surface px-4 text-xs font-bold text-fg hover:bg-surface-muted">Limpar filtros</button>
        </div>
      )}
    </>
  );
}
