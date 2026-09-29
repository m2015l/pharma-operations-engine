# Frontend v2: padrão visual da Solufarma + exportação .docx

> Especificação para um dev executar. Escrita em 29/09/2026 a partir dos pedidos do cliente (via Roger) e das 4 telas do sistema interno **Contratos** em `frontend/acesso/`.
> Estado de partida: `frontend/` (Next.js 16.3 + Tailwind v4 + shadcn/ui) e `api/` (FastAPI) descritos em `docs/DIARIO_DE_BORDO_FRONTEND.md`, entrada de 29/09.

## 1. Objetivo e escopo

**Objetivo:** o assistente de licitações passa a parecer um irmão do sistema Contratos (mesma paleta, mesmo header, mesma organização) e ganha **exportação da conversa para Word**.

**Muda:**
- Paleta, fonte e tokens (`globals.css`, `layout.tsx`).
- A barra lateral escura vira um **header branco** no padrão Contratos, com a navegação à direita.
- Cada tela (Consulta, Acervo, Enviar) é reorganizada no padrão "título grande + subtítulo + cards brancos sobre fundo cinza".
- Nova rota `POST /exportar/docx` na API e botões de exportar na Consulta.
- Login CPF + PIN entra no plano (fatia própria, depende de uma resposta do Roger).

**Não muda:**
- Os contratos `POST /perguntar`, `GET /documentos`, `GET /documentos/{id}/fonte` e `POST /upload`.
- O comportamento do chat: histórico de 6 turnos, "Nova consulta", marcadores `[n]` clicáveis, painel de fontes, visualizador pdf.js e régua de rastreabilidade.
- O modo demonstração e o proxy `/api/*` do Next.
- O RAG (`src/solufarma_rag`).

**Fica obsoleto no `frontend/CONCEITO.md`** (não editar agora; atualizar quando a v2 entrar):
- A seção "Direção visual" inteira: violeta de carimbo, Archivo, Source Serif 4 e o uso amplo de IBM Plex Mono.
- A frase "aviso fixo na barra lateral", porque a barra lateral deixa de existir.

---

## 2. Referência visual: o sistema Contratos

### 2.1 O que as telas mostram

| Elemento | Observado |
|---|---|
| **Base técnica** | Os tons auxiliares batem **exatamente** com o tema **Bootswatch Flatly** do Bootstrap 5: `#18bc9c` (success), `#2c3e50` (dark), `#95a5a6` (secondary), `#ecf0f1` (light), com o *primary* trocado por `#124443`. Flatly usa **Lato**, e as letras das capturas são compatíveis com ela. Conclusão: **a fonte é Lato** (confirmar com quem mantém o Contratos, junto com o SCSS de variáveis). |
| **Header** | Branco, ~60 px de altura. À esquerda, o logo SOLUFARMA ENGENHARIA (~230×36 px), um divisor vertical cinza de 1 px e o nome do módulo ("Contratos", ~18 px, peso 500–600, verde-petróleo). Embaixo, uma **borda de 2 px `#124443`**. |
| **Ações do header** | Ficam à direita e são botões *outline* pequenos, com borda cinza-escura, texto escuro, raio ~4 px e altura ~30 px ("Painel de prazos", "Status de seguros"). **O item ativo fica preenchido** em `#124443` com texto branco. Depois vêm o nome do usuário em cinza, o badge "Admin" (teal com texto branco, pílula pequena) e os botões "Alterar PIN" e "Sair" em *outline* claro. |
| **Fundo da página** | `#ecf0f1`, um cinza-claro levemente esverdeado. |
| **Título da página** | Grande (~36–40 px), peso regular, quase preto, sem negrito. Logo abaixo, um subtítulo pequeno (~14 px) em cinza (`#555`) com o contexto, por exemplo "As obras vêm do SCAM — … Última sincronização: …". |
| **Ação da página** | Botão *outline* médio alinhado à direita do título ("Sincronizar com o SCAM"). |
| **Cards** | Brancos, raio ~6 px, sombra muito leve, sem borda visível e padding ~16 px. |
| **Botão primário** | Preenchido em `#124443`, texto branco e **largura total do card** ("Entrar", "Filtrar"). |
| **Links** | Teal sublinhados ("Esqueci meu PIN"). No breadcrumb, verde-escuro sublinhado com seta "←". |
| **Badges de status** | Pílulas pequenas e em negrito: "Concluída" em `#2c3e50`, "Planejada" em `#95a5a6`, "Ativo" em teal. |
| **Mestre-detalhe (Obras)** | À esquerda (~40%), um card de filtro (Buscar + Status + Filtrar), um contador "404 obras no total." e a lista rolável (código, título, subtítulo em cinza, badge). À direita (~60%), um card com o detalhe e um estado vazio "Selecione uma obra na lista…". |
| **Painel de prazos** | Uma legenda com bolinhas coloridas e três cards-contadores (vermelho, amarelo, verde). A linha de filtros é horizontal. A tabela tem cabeçalho em negrito sem fundo e linhas tingidas pela cor de status. "Exportar para Excel" é um botão preenchido em teal, e "Filtrar" desabilitado aparece em cinza `#95a5a6`. |
| **Formulário (Contrato)** | Um breadcrumb e título grande. Os metadados vêm em linhas de texto e o status em badge. Ações "Editar" (outline cinza) e "Apagar" (outline vermelho). O formulário fica em card branco com rótulos acima dos campos, em duas colunas. |
| **Rodapé** | Texto discreto em cinza, alinhado à esquerda: "Contratos Solufarma — controle de prazos por obra". |
| **Login** | Um card centralizado de ~470 px com o título "Entrar", os campos CPF (placeholder `000.000.000-00`) e PIN ("4 números"), o botão primário "Entrar" em largura total e o link "Esqueci meu PIN". No header aparece só o botão "Entrar". |

### 2.2 Paleta extraída (hex aproximados, medidos nos pixels das capturas)

| Papel | Hex | Origem |
|---|---|---|
| Verde-petróleo (**oficial**) | `#124443` | Botão primário, item ativo e borda do header (medido `#124443` / `#184241`) |
| Teal (**oficial**) | `#44a18c` | Link "Esqueci meu PIN" (medido `#44a18c`) |
| Branco (**oficial**) | `#ffffff` | Header e cards |
| Fundo da página | `#ecf0f1` | Medido exato (Flatly *light*) |
| Teal dos badges e botões do Contratos | `#18bc9c` | "Admin", "Ativo", paginação, "Exportar para Excel" (Flatly *success*, **não é** o teal oficial) |
| Texto de título | `#1a1a1f` ≈ `#212529` | Medido nos títulos |
| Texto secundário | `#555452` ≈ `#5b5b5b` | Subtítulos |
| Rodapé | `#8b9096` | Contraste 2,8:1 sobre o fundo (reprova AA) |
| Borda de input | `#dadee1` ≈ `#dee2e6` | Bootstrap padrão |
| Badge escuro | `#2c3e50` | "Concluída" |
| Badge ou botão neutro | `#95a5a6` | "Planejada" e botão desabilitado |
| Status vermelho | fundo `#f9e9ea`, ponto/texto `#bb5b69` | Painel de prazos |
| Status amarelo | fundo `#fff6d9`, ponto/texto `#9d7827` | Painel de prazos |
| Status verde | fundo `#e7f4eb`, ponto/texto `#3f7e53` | Painel de prazos |
| Perigo (outline) | ≈ `#e74c3c` | "Apagar" (Flatly *danger*) |

### 2.3 Contraste WCAG (calculado)

| Combinação | Razão | AA texto normal (4,5) | AA texto grande / UI (3,0) |
|---|---|---|---|
| Branco sobre `#124443` | **10,86** | passa (também AAA) | passa |
| Branco sobre `#44a18c` | **3,12** | **reprova** | passa |
| `#44a18c` sobre branco (link) | 3,12 | **reprova** | passa |
| `#44a18c` sobre `#ecf0f1` | 2,72 | reprova | **reprova** |
| `#124443` sobre `#44a18c` | 3,48 | reprova | passa |
| Branco sobre `#18bc9c` (badge do Contratos) | 2,41 | reprova | reprova |
| `#124443` sobre `#ecf0f1` | 9,46 | passa | passa |

**Como tratar o teal:** o `#44a18c` oficial fica para o que **não é texto pequeno**: bordas, traços da régua, anel de foco sobre branco, ícones ≥ 16 px sobre branco, fundos de hover e texto ≥ 24 px (ou ≥ 18,66 px em negrito). Para **texto e fundo de badge ou marcador**, entra um degrau mais escuro da mesma família, o **`--teal-texto: #277160`**. Ele dá 5,81:1 sobre branco, 5,06:1 sobre `#ecf0f1` e 5,1:1 sobre o teal-claro `#e6f3ef`, e visualmente continua sendo "o teal". Não copiar o `#18bc9c` do Contratos, que reprova até como UI.

### 2.4 Tokens propostos (`src/app/globals.css`)

Substituem o bloco `:root` atual. Os nomes semânticos do shadcn continuam os mesmos, então os componentes de `ui/` não mudam. Os nomes próprios (`--papel`, `--carimbo` etc.) são renomeados, e é preciso buscar e trocar o uso das classes nas telas.

```css
:root {
  /* Marca (oficial) */
  --petroleo: #124443;        /* primário: botões, item ativo, borda do header */
  --petroleo-hover: #0d3332;
  --teal: #44a18c;            /* só decorativo/UI grande: bordas, régua, foco, ícones */
  --teal-texto: #277160;      /* teal para TEXTO e fundos de marcador/badge (AA) */
  --teal-claro: #e6f3ef;      /* fundo de marcador inativo, hover de fonte */

  /* Neutros (Flatly) */
  --fundo: #ecf0f1;
  --folha: #ffffff;
  --tinta: #212529;           /* texto principal e títulos */
  --grafite: #5b6b6e;         /* texto secundário: 4,85:1 sobre o fundo */
  --linha: #dee2e6;
  --neutro: #95a5a6;          /* badge "neutro"/desabilitado (texto branco só em ≥ 14px bold) */

  /* Status (painel de prazos) */
  --ok: #3f7e53;      --ok-claro: #e7f4eb;
  --alerta: #7a5a0a;  --alerta-claro: #fff6d9;   /* 5,9:1 */
  --erro: #b42318;    --erro-claro: #f9e9ea;     /* 6,57:1 sobre branco */

  /* shadcn */
  --background: var(--fundo);
  --foreground: var(--tinta);
  --card: var(--folha);
  --card-foreground: var(--tinta);
  --popover: var(--folha);
  --popover-foreground: var(--tinta);
  --primary: var(--petroleo);
  --primary-foreground: #ffffff;
  --secondary: #ffffff;               /* botão outline do header */
  --secondary-foreground: var(--tinta);
  --muted: #f4f6f7;
  --muted-foreground: var(--grafite);
  --accent: var(--teal-claro);
  --accent-foreground: var(--petroleo);
  --destructive: var(--erro);
  --border: var(--linha);
  --input: #ced4da;
  --ring: var(--teal);
  --radius: 0.375rem;                 /* Bootstrap 5 */
  --sombra-card: 0 1px 2px rgb(18 68 67 / 0.06), 0 1px 3px rgb(0 0 0 / 0.04);
}
```

**Fonte:** usar **Lato** via `next/font/google`. Ela não é variável, então o `weight` é obrigatório: `["400", "700"]`, e `"300"` se o título grande ficar pesado (ver `node_modules/next/dist/docs/01-app/03-api-reference/02-components/font.md`).
- `--font-sans` passa a ser Lato.
- **Sai** Source Serif 4, e sai Archivo.
- IBM Plex Mono sai também. Os números passam a usar `font-variant-numeric: tabular-nums`, mas antes é preciso conferir no navegador se a Lato do Google Fonts tem essa feature. Se não tiver, a Plex Mono fica só em páginas, contagens e marcadores.

---

## 3. Mapeamento tela a tela

### 3.1 Moldura comum (substitui `BarraLateral`)

Criar `components/cabecalho.tsx` e `components/rodape.tsx` e apagar `barra-lateral.tsx`. O `layout.tsx` passa a ser uma coluna: cabeçalho, `<main>` e rodapé, sobre `--fundo`.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ [LOGO SOLUFARMA] │ Licitações  (Demonstração)     [Consulta] [Acervo] [Enviar documento]  │  branco, 60px
│                                                     ▲ ativo = preenchido #124443          │
│                                                     (depois do login: Nome [Admin] [Sair])│
╞══════════════════════════════════════════════════════════════════════════════════════════╡  2px #124443
│  fundo #ecf0f1 · conteúdo max-w ~1480px · padding lateral 32–48px                         │
│  ...                                                                                      │
│  Licitações Solufarma — consulta ao acervo técnico                  (rodapé, 13px, cinza) │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Navegação:** três links com cara de botão *outline* pequeno (h-8, px-3, 14 px), o ativo preenchido em `--petroleo`. Precisam continuar sendo `role=link` com os nomes "Consulta", "Acervo" e "Enviar documento", porque o `demo/gravar_demo.py` depende disso.
- **Modo demonstração:** hoje é um card na barra lateral. Vira um **badge ao lado do nome do módulo** ("Demonstração", fundo `--alerta-claro`, texto `--alerta`) com tooltip "Respostas gravadas das auditorias. Nenhuma consulta é cobrada."
- **Modo real:** sem badge.
- **Sem API:** badge `--erro` "Sem conexão com a API".
- **Logo:** até chegar o arquivo oficial (seção 6), usar o texto "SOLUFARMA" em Lato 700, `--petroleo`, com "ENGENHARIA" pequeno e espaçado embaixo. Deixar o componente `<Logo />` pronto para trocar por `next/image`.
- **Largura mínima:** continua 1024 px.

### 3.2 Consulta (`/`): mestre-detalhe como a tela Obras

```
 Consulta ao acervo                                          [⤓ Exportar .docx] [↺ Nova consulta]
 Toda resposta indica o documento e a página de onde a informação saiu.

┌───────────────────────────────────────────────────┐  ┌────────────────────────────────────┐
│ 01  A gente já fez obra de implantação de labo...?│  │ Fontes · resposta 1                │
│  ┌───────────────────────────────────────────────┐│  │ ┌────────────────────────────────┐ │
│  │ Sim. A Solufarma executou... [1] ... [3]      ││  │ │[1] SENAI CETIQT                │ │
│  │ (Lato 16–17px, lh 1.65, máx ~70ch)            ││  │ │ CAT 576640 · p. 3 · Seção 2    │ │
│  │ ▮▮▯▮▯▯▯▯ 3 citadas de 8 trechos    [⤓ .docx]  ││  │ │ │ "trecho..."                  │ │
│  └───────────────────────────────────────────────┘│  │ │              [Ver a fonte →]   │ │
│ 02  E o valor disso?                              │  │ └────────────────────────────────┘ │
│  ...                                  (rola)      │  │  ...                    (rola)     │
├───────────────────────────────────────────────────┤  │                                    │
│ [ Pergunte ao acervo…                 ] [Perguntar]│  │                                    │
│ Enter envia · Shift+Enter quebra linha …          │  │                                    │
└───────────────────────────────────────────────────┘  └────────────────────────────────────┘
        card branco (~60%)                                  card branco (~40%, mín 380px)
```

- O título e o subtítulo seguem o padrão da página, e as ações ficam à direita, como "Sincronizar com o SCAM". **Exportar .docx** usa *outline* e fica desabilitado sem nenhuma resposta ou com uma consulta em andamento. "Nova consulta" também usa *outline*.
- Os dois cards ocupam a altura restante da viewport, cada um com rolagem própria. O compositor fica **dentro** do card da conversa, preso ao rodapé dele.
- **Estado vazio** ("O que você precisa comprovar?"): os exemplos viram uma lista no estilo da lista de Obras, com linhas separadas por borda e hover em `--teal-claro`. O card de Fontes vazio mostra "Clique num marcador [n] para ver aqui de onde a informação saiu.", no mesmo tom de "Selecione uma obra na lista…".
- **Resposta:** um bloco com borda `--linha`, e quando está selecionado a borda passa a `--teal` com 2 px à esquerda. No rodapé ficam a régua (traços citados em `--teal`, os outros em `--linha`) e o botão pequeno **"⤓ .docx"**, que exporta só esta resposta (seção 4.2). Em modo demo aparece também "Resposta gravada · auditoria de dd/mm".
- **Marcador `[n]`:**
  - inativo: fundo `--teal-claro`, borda `--teal`, texto `--teal-texto`;
  - ativo ou hover: fundo `--teal-texto` com texto branco.
- **Faixa "Resposta sem fonte rastreável":** fundo `--alerta-claro`, texto `--alerta` e ícone. Marcador inexistente continua riscado.
- **"Nada encontrado no acervo":** badge neutro (`#2c3e50` com texto branco, como "Concluída"), porque é uma recusa correta e não um erro.
- **Botão Perguntar:** primário `--petroleo`.
- **Ficha de fonte:**
  - órgão em caixa-alta pequena `--grafite`, título em 700 e "p. 3 · Seção" em `--grafite`;
  - citação com barra `--teal` à esquerda;
  - "Ver a fonte" como link-botão em `--teal-texto`, sublinhado no hover;
  - ficha ativa com borda `--teal` e anel `--teal-claro`.
- O `demo/gravar_demo.py` usa `aside ol > li`. Manter o painel de fontes como `<aside>` com `<ol>`, ou atualizar o script na mesma PR.

### 3.3 Acervo (`/acervo`): tabela como o Painel de prazos

```
 Acervo                                                              [⤒ Enviar documento]
 12 documentos · 1.834 trechos pesquisáveis. Só o que está aqui entra nas respostas.

 ● Indexado   ● Em processamento   ● Erro            (legenda como a do painel de prazos)

┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Buscar [ título ou órgão…                     ]   Tipo [ Todos ▾ ]                        │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Documento                        Tipo        Páginas  Trechos  Indexado em  Situação      │
│ SENAI CETIQT                     [Atestado]       60      112  28/09/2026   [Indexado]  Abrir PDF │
│ CAT 576640 …                                                                             │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Título "Acervo":** o `demo/gravar_demo.py` espera o texto **"Documentos indexados"**. Ou se mantém esse texto como subtítulo de seção dentro do card, ou se atualiza o script.
- **Busca e filtro por tipo:** filtram no cliente, porque o acervo é pequeno. Isso é novo, mas custa pouco e segue o padrão Obras.
- **Situação:** badge em pílula.
  - Indexado: fundo `--teal-texto`, texto branco.
  - Em processamento: `--alerta-claro` / `--alerta`.
  - Erro: `--erro-claro` / `--erro`.
- **Linhas:** sem tingimento. O tingimento do painel de prazos serve para urgência, e aqui não há urgência.
- **"Abrir PDF":** link em `--teal-texto`, porque leva a documento.

### 3.4 Enviar documento (`/enviar`): formulário como "Novo seguro"

```
 ← Acervo
 Enviar documento
 Atestados, CATs, editais e atas em PDF, de até 50 MB.

┌──────────────────────────────────────────────────┐   ┌───────────────────────────────┐
│ ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐  │   │ O que acontece depois do envio│
│   Arraste o PDF para cá  ou  [Escolher arquivo]  │   │ (texto honesto: hoje o arquivo │
│ └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │   │  só é validado — decisão 7)    │
│ Órgão contratante            Tipo de documento   │   └───────────────────────────────┘
│ [Ex.: Instituto Butantan ]   [Atestado / CAT ▾]  │
│ [            Enviar documento (largura total) ]  │
└──────────────────────────────────────────────────┘
```

- O botão primário ocupa **a largura total** do card, como "Entrar" e "Filtrar". Área de arraste com borda tracejada `--linha`, que fica `--teal` ao arrastar.
- **Texto do card lateral:** passa a descrever o comportamento atual ("nesta versão o arquivo é validado mas ainda não é indexado; a indexação é feita pela equipe"). Isso resolve a decisão 7. Quando o upload real entrar, o texto volta a falar em segundo plano.
- O script de demo depende do texto "Novo documento para o acervo", do rótulo "Órgão contratante" e do botão "Enviar documento". Manter esses textos ou atualizar o script.

### 3.5 Entrar (`/entrar`): **não implementar agora**, só registrado

É a cópia do login do Contratos: um card de ~470 px centralizado com "Entrar", CPF (máscara `000.000.000-00`), PIN (4 dígitos, `inputmode="numeric"`, `type="password"`), o botão primário "Entrar" em largura total e o link teal "Esqueci meu PIN". No header ficam só o logo, o módulo e "Entrar". Depois do login, o header mostra o nome, o badge de perfil, "Alterar PIN" e "Sair". A decisão que bloqueia está na pergunta 3 (seção 8).

---

## 4. Exportação para .docx

### 4.1 Recomendação técnica: **gerar no backend com `python-docx`** (`POST /exportar/docx`)

| Critério | Navegador (`docx` do npm) | Backend (`python-docx`) |
|---|---|---|
| O histórico vive só no navegador | Vantagem: não precisa enviar nada | O navegador envia os turnos que já tem, com `RespostaOut` inteiro, e a API só formata. Não há nova chamada ao LLM, então **é custo zero também no modo real** |
| Futuro histórico persistido (login) | Continuaria no cliente | Troca natural para `GET /conversas/{id}/docx` reaproveitando o mesmo gerador |
| Estilo e paleta do documento | Definidos em TS, separados do CSS de qualquer forma | Estilos num só módulo Python, com logo lido de `api/assets/` |
| Peso do bundle | Soma a biblioteca `docx` (centenas de KB) a uma tela que já carrega o pdf.js | Zero no bundle |
| Testabilidade | Precisa de um teste de DOM ou Node à parte | `pytest` sobre `api/fixtures/demo.json`: gera, reabre com `python-docx` e confere títulos, marcadores e fontes. Cabe no `tests/` que já existe |
| Consistência | É a única lógica de negócio em TS | O projeto é Python, e o `tools/` pode reusar o gerador (por exemplo, exportar respostas de auditoria) |

**Conclusão:** backend. O único argumento contra é "o histórico está no navegador", e ele se resolve mandando o histórico no corpo do POST. O download chega pelo proxy `/api/*` que já existe, como binário.

### 4.2 Requisitos

- **Conversa inteira (padrão):** o botão "Exportar .docx" no header da Consulta exporta todos os turnos que têm resposta. Turnos com erro entram com a pergunta e a nota "Sem resposta (erro: …)". O turno em andamento não entra, e o botão fica desabilitado enquanto houver um.
- **Resposta isolada:** vale a pena, porque é o caso "colar no envelope da licitação". Há um botão pequeno "⤓ .docx" no rodapé de cada resposta. Ele usa **a mesma rota**, com um único turno. O documento tem o mesmo layout, e o título do cabeçalho fica no singular.
- **Nome do arquivo:**
  - conversa: `consulta-solufarma-AAAA-MM-DD-HHMM.docx`;
  - resposta isolada: `resposta-solufarma-AAAA-MM-DD-HHMM.docx`.
  - A hora vem de `gerado_em`, no fuso de São Paulo. A API define o nome no `Content-Disposition` e o frontend o usa ao salvar.
- **Download no frontend:** `fetch` seguido de `blob`, `URL.createObjectURL` e um `<a download>`. Sucesso ou erro aparecem num toast (`sonner`, que já está instalado).

### 4.3 Contrato de dados

Em `api/schemas.py`:

```python
class TurnoExportado(BaseModel):
    pergunta: str = Field(min_length=1, max_length=2000)
    perguntado_em: datetime | None = None      # novo campo no Turno do frontend
    resposta: RespostaOut | None = None        # exatamente o que /perguntar devolveu
    erro: str | None = None

class ExportarDocxIn(BaseModel):
    escopo: Literal["conversa", "resposta"] = "conversa"
    gerado_em: datetime                        # com fuso; vem do navegador
    usuario: str | None = None                 # preenchido quando houver login
    turnos: list[TurnoExportado] = Field(min_length=1, max_length=100)
```

- **Resposta:** `200` com `application/vnd.openxmlformats-officedocument.wordprocessingml.document` e `Content-Disposition: attachment; filename="consulta-solufarma-2026-09-29-1432.docx"`.
- **Erros:** `422` para validação e `413` se o corpo passar de ~5 MB, o que já seria uma conversa absurda.
- **Frontend:**
  - `api.exportarDocx(corpo) → Promise<Blob>` em `lib/api.ts`;
  - o `Turno` do `ConversaProvider` ganha `perguntadoEm: string` (ISO), preenchido em `perguntar()`.
- **Segurança:** a API só formata o que recebe. O documento diz que o conteúdo é gerado por IA e deve ser conferido, e não é um registro oficial.

### 4.4 Layout do documento

Página A4, margens de 2,5 cm, fonte **Lato** declarada (o Word troca por Calibri se ela não estiver instalada, o que é aceitável) e corpo em 11 pt.

```
┌────────────────────────────────────────────────────────────┐
│ [logo]  SOLUFARMA ENGENHARIA · Licitações                  │ cabeçalho de página (todas),
│ ────────────────────────────────────────── (linha #124443) │ texto #124443
│                                                            │
│ Consulta ao acervo técnico                  (título 20pt)  │
│ Gerado em 29/09/2026 às 14:32 · 3 perguntas · por Fulano   │ 10pt cinza
│ [Modo demonstração — respostas gravadas das auditorias]    │ só se modo=demo
│                                                            │
│ Pergunta 1                                (12pt, #124443)  │
│ A gente já fez obra de implantação de laboratório?  (bold) │
│                                                            │
│ Resposta                                                   │
│ Sim. A Solufarma executou … [1] … [3].                     │ [n] em negrito #277160
│ • listas e **negrito** do markdown preservados             │
│ ⚠ Resposta sem fonte rastreável. Não use sem conferir.     │ se contrato_citacao_ok=false
│ 3 citadas de 8 trechos recuperados                (9pt)    │
│                                                            │
│ Fontes                                                     │ tabela sem bordas verticais,
│ [1] SENAI CETIQT — CAT 576640 … · Atestado · Seção 2 · p. 3│ cabeçalho #124443/branco
│     "trecho citado…" (itálico, 9pt, até ~400 caracteres)   │
│ [3] …                                                      │
│ ─────────────────────────────────────────────────────────  │
│ Pergunta 2 …                                               │
├────────────────────────────────────────────────────────────┤
│ Resposta gerada por IA a partir do acervo da Solufarma.    │ rodapé de página (todas),
│ Confira sempre no documento original antes de usar.  p. 1/3│ 8pt cinza + nº de página
└────────────────────────────────────────────────────────────┘
```

- **Campos de cada fonte:** marcador, órgão, título do documento, tipo, seção e página (ou "p. X–Y"), com o trecho citado limpo pela mesma regra do `limparTrecho` do painel.
- **Marcadores e fontes:** só as fontes **citadas** entram, porque `citacoes` já vem filtrado. Um marcador inválido aparece riscado e acompanhado de "(fonte inexistente)".
- **Markdown:** o texto da resposta é markdown. Basta um conversor mínimo (parágrafo, lista `-`/`1.`, `**negrito**` e `[n]`) em `api/exportar_docx.py`, testado com todas as respostas de `demo.json`. Se aparecer um caso que ele não cobre, entra o `markdown-it-py`.
- **Nada encontrado:** a resposta aparece com o rótulo "Nada encontrado no acervo" e sem a seção de fontes.
- **Numeração de página:** o campo `PAGE`/`NUMPAGES` via XML (o `python-docx` não expõe a API; são ~10 linhas de `OxmlElement`).
- **Links entre `[n]` e a fonte** (bookmarks): ficam fora da v2.

---

## 5. Decisões de design antigas (diário de 29/09)

| # | Decisão | Destino |
|---|---|---|
| 1 | Fundo cinza-azulado, texto azul-marinho, violeta de carimbo | **Revogada**. Entram a paleta Solufarma e os tokens da seção 2.4. A **regra se mantém, reinterpretada:** o **teal** marca o que é rastreável ou leva a documento (marcadores, fichas de fonte, régua, "Ver a fonte", "Abrir PDF"). No Contratos o teal já é a cor de link, então as duas convenções coincidem. As ações usam `--petroleo` e nunca teal. |
| 2 | Archivo, Source Serif 4 nas respostas e IBM Plex Mono | **Revogada**. Tudo em **Lato**, a fonte da empresa. A sensação de "ler um documento" passa a vir do layout (card branco, 16–17 px, entrelinha 1,65, linha de ~70 caracteres) e não da serifa, e o documento Word cumpre esse papel de leitura. A Plex Mono só sobrevive se a Lato não tiver tabular-nums. |
| 3 | Régua de rastreabilidade | **Mantida**, agora com traços em `--teal`. |
| 4 | Visualizador pdf.js próprio | **Mantida.** Só o cabeçalho do diálogo ganha os tokens novos. |
| 5 | Só tema claro, desktop ≥ 1024 px, conversa persistente e "Nova consulta" | **Mantida.** O Contratos também só tem tema claro. |
| 6 | `demo.json` e vídeos fora do git | **Continua pendente**, porque é independente do visual. Vale a mesma regra para os `.docx` de exemplo gerados em testes: gravar em `.tmp/` e nunca commitar. |
| 7 | Texto enganoso na tela de upload | **Resolvida na fatia F4**: o texto passa a descrever o comportamento atual. |

---

## 6. Ativos necessários do cliente

| Ativo | Por quê | Hoje |
|---|---|---|
| **Logo SOLUFARMA ENGENHARIA em SVG**, ou PNG ≥ 600 px de largura com fundo transparente | Header e cabeçalho do .docx (o Word aceita PNG; SVG → PNG na API) | Não temos. Recortar das capturas do WhatsApp não serve, porque a resolução e a compressão são ruins |
| Versão só do símbolo "S", quadrada | Favicon (`src/app/icon.png` 512×512) e ícone do app | O `favicon.ico` padrão do Next |
| Confirmação da fonte (Lato?) e o SCSS ou as variáveis do Contratos | Evitar divergência de tom, raio e sombra | Deduzido: Bootswatch Flatly + primary `#124443` |
| Nome oficial do módulo | Header, `<title>`, rodapé e .docx | Pergunta 1 |

---

## 7. Plano de implementação

Cada fatia é um PR pequeno na `main`. A ordem importa: F1 destrava F2–F4, e F5 destrava F6. Estimativas: P ≈ meio dia, M ≈ 1 dia, G ≈ 2–3 dias. Toda fatia de frontend termina com `npm run lint`, `npm run build` e o `demo/gravar_demo.py` rodando em modo demo (seletores atualizados se mudaram). **Nada disso exige `MODO_DEMO=0`.**

| Fatia | O quê | Aceite | Tam. |
|---|---|---|---|
| **F0 · Tokens e fonte** | Trocar o `:root` e o `@theme` do `globals.css` pelos tokens da seção 2.4. Lato no `layout.tsx`; tirar Archivo, Source Serif e (se possível) Plex Mono. Classe `.resposta` em Lato. Buscar e trocar `carimbo`, `papel` e `tinta` nas telas | Nenhum violeta sobra (`grep -r carimbo src` vazio). Fundo `#ecf0f1`. Build ok | P |
| **F1 · Moldura** | `cabecalho.tsx` (logo em texto, divisor, módulo, badge de modo, nav com o item ativo preenchido), `rodape.tsx` e `layout.tsx` em coluna. Apagar `barra-lateral.tsx` | O header bate com a captura do Contratos lado a lado. Borda de 2 px `#124443`. Navegação por teclado com foco visível. O script de demo navega pelos links | M |
| **F2 · Consulta** | Título, subtítulo e ações. Os dois cards mestre-detalhe com rolagem própria. Marcadores, fichas, régua, faixa de alerta e badge "Nada encontrado" nos tokens novos. Compositor dentro do card | O fluxo do vídeo demo (pergunta, [3], [5], Ver a fonte, seguimento com pronome) funciona igual. Texto e marcadores ≥ 4,5:1 (checar no DevTools) | M |
| **F3 · Acervo** | Título e subtítulo, legenda, card com busca e filtro por tipo no cliente, badges de situação e "Abrir PDF" em teal | A busca filtra por título e órgão. O script encontra a tela | P |
| **F4 · Enviar** | Breadcrumb, card do formulário, botão em largura total, card lateral com o texto honesto (decisão 7) | O envio de PDF sintético mostra "recebido". O texto não promete indexação | P |
| **F5 · API .docx** | `python-docx` em `api/requirements.txt`. Schemas da seção 4.3. `api/exportar_docx.py` (gerador puro: `gerar(ExportarDocxIn) -> bytes`) e a rota `POST /exportar/docx` em `main.py`. Logo lido de `api/assets/logo.png` se existir, com fallback em texto. Teste `tests/test_exportar_docx.py` que gera a partir de todas as respostas de `demo.json` e reabre o arquivo | O teste passa. O arquivo abre no Word e no LibreOffice sem aviso de reparo. Cabeçalho, rodapé com aviso e nº de página, `[n]` e fontes corretas. O nome do arquivo segue o padrão. Zero chamada ao LLM | M |
| **F6 · Botões de exportar** | `perguntadoEm` no `Turno`, `api.exportarDocx` e o download por blob. Botão "Exportar .docx" no header da Consulta e "⤓ .docx" em cada resposta. Toast de erro | A conversa inteira e a resposta isolada baixam com o nome certo. Botão desabilitado sem respostas ou durante uma consulta | P |
| **F7 · Logo, favicon e metadados** | Trocar o logo em texto pelo arquivo oficial, `icon.png`, `<title>` "Licitações · Solufarma" (ou o nome escolhido) | Depende dos ativos da seção 6 | P |
| **F8 · Login CPF + PIN** | Tela `/entrar`, sessão, proteção das rotas da API, nome e perfil no header, "Alterar PIN" e "Sair". Abre caminho para o histórico persistido e o `GET /conversas/{id}/docx` | **Bloqueada pela pergunta 3.** Fora desta rodada | G |

**Depois da v2:** atualizar a seção "Direção visual" do `CONCEITO.md` e regravar o vídeo demo.

---

## 8. Respostas do Roger (29/09)

1. **Nome do módulo: "Licitações".** Vale para o header, o `<title>` ("Licitações · Solufarma"), o rodapé e o .docx.
2. **Logo:** o arquivo oficial está em `frontend/acesso/Logo.png` (PNG, verde-petróleo, "SOLUFARMA" com "ENGENHARIA" embaixo). Com ele, a F7 deixa de estar bloqueada e o logo em texto da F1 pode ser pulado. Também serve de fonte para o `api/assets/logo.png` do .docx (F5). A fonte continua deduzida (Lato/Flatly), sem confirmação formal.
3. **Login: fora desta rodada.** O Roger vai confirmar com o gerente se deve existir tela de login; se sim, construímos depois. A F8 fica suspensa, não só bloqueada.
4. **Trecho citado no .docx: sim**, incluir um pedaço do trecho de cada fonte (até ~400 caracteres) para dar precisão e permitir conferir sem abrir o PDF.
5. **Autor no .docx: não.** O documento sai sem autor.
6. **Aviso de rodapé: aprovado como proposto:** "Resposta gerada por IA a partir do acervo da Solufarma. Confira sempre no documento original antes de usar."
