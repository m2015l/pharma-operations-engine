# Hospedagem: onde colocar o assistente para a equipe usar

> Roteiro de decisão para o Roger, escrito em 30/09/2026. Os preços foram consultados nesse dia nos
> sites oficiais (fontes no fim). Valores em US$ por mês, sem imposto e sem o custo de uso do LLM,
> do OCR e dos embeddings, que é **igual em todas as opções** e depende só de quantas perguntas e
> envios forem feitos.

## O que o sistema exige de quem hospeda

Isto vem do código atual (`api/main.py`, `api/ingestao.py`, `frontend/next.config.ts`) e vale para
qualquer opção:

| Característica | Consequência para a hospedagem |
|---|---|
| O navegador só fala com o Next, e o Next repassa `/api/*` para a API em `:8000` | Só o Next precisa ser acessível. A API pode (e deve) escutar só em `127.0.0.1`. |
| **A API não tem login nem chave própria** (ADR-009). Quem alcança `/perguntar` ou `/upload` gasta dinheiro e lê o acervo | Nenhuma URL da API pode ficar aberta na internet. Se o site for público, **algo** precisa pedir senha antes. |
| O upload roda o pipeline numa thread dentro do processo da API (1 por vez), com etapas de minutos (OCR) | O processo precisa ficar **sempre ligado**. Serverless (Vercel Functions, Lambda, Cloud Run escalando a zero, plano grátis do Render que "dorme") **não serve para a API**: mata o trabalho no meio. |
| O estado dos envios fica em memória (`_ENVIOS`) | Reiniciar a API apaga a lista da tela "Enviar"; o documento já cadastrado não se perde. Hosts que reiniciam a cada deploy tornam isso mais visível. |
| O PDF vai para `data/brutos/` e o texto extraído para `data/extraidos/` antes de subir para o Supabase Storage (etapa "cadastro") | O disco local é só **área de passagem**: depois do cadastro, a fonte da verdade é o Storage + Postgres. Disco efêmero é aceitável; perde-se apenas um envio que estava no meio durante um reinício (reenviar resolve). Não é obrigatório migrar `data/brutos/` para o Storage. |
| Chaves no `.env` da raiz (Supabase service key, OpenRouter, Voyage) | Ficam só na máquina da API. O Next não precisa de nenhuma chave, só de `API_URL`. |
| Supabase está em `sa-east-1` (AWS São Paulo) | A API faz várias consultas ao banco por pergunta. Rodar a API no Brasil deixa a resposta mais rápida; nos EUA ou na Europa soma ~120–200 ms por ida e volta ao banco. |
| Memória: PyMuPDF renderizando páginas para OCR + LangChain + Next | 2 GB de RAM no mínimo para API e Next juntos; 512 MB não aguenta o OCR. |

**Proteção comum a todas as opções (faça em qualquer caso):**
1. Pôr **limite de gasto na chave do OpenRouter** (o painel do OpenRouter permite limite de crédito
   por chave) e alerta de uso na Voyage. É o que segura o prejuízo se algo vazar.
2. Manter `UPLOAD_MAX_PAGINAS_OCR` (padrão 60): envio grande espera aprovação antes de gastar.
3. `.env` só na máquina da API, nunca em pasta sincronizada (OneDrive) nem no git.

---

## Opção A: um PC da empresa na rede interna (Windows)

O assistente roda num computador do escritório que fica sempre ligado. A equipe abre
`http://<nome-ou-ip-do-pc>:3000` no navegador. Nada fica exposto à internet.

**Passos**
1. Escolher o PC: sempre ligado, sem suspensão, com pelo menos 8 GB de RAM (não usar o notebook
   pessoal do Roger). Pedir ao responsável pela rede um **IP fixo** (reserva de DHCP no roteador)
   ou usar o nome do PC.
2. Clonar o repositório **fora do OneDrive** (ex.: `C:\solufarma`), copiar o `.env` e criar o
   ambiente: `uv sync` e `uv pip install -r api/requirements.txt`; no `frontend/`, `npm ci` e
   `npm run build`.
3. Registrar dois serviços que sobem sozinhos com o Windows, via NSSM:
   ```powershell
   nssm install SolufarmaAPI C:\solufarma\.venv\Scripts\python.exe "-m uvicorn main:app --app-dir api --host 127.0.0.1 --port 8000"
   nssm set SolufarmaAPI AppDirectory C:\solufarma
   nssm set SolufarmaAPI AppEnvironmentExtra MODO_DEMO=0

   nssm install SolufarmaWeb "C:\Program Files\nodejs\node.exe" "node_modules\next\dist\bin\next start -H 0.0.0.0 -p 3000"
   nssm set SolufarmaWeb AppDirectory C:\solufarma\frontend
   ```
   `python -m uvicorn`, e não `uvicorn.exe`, porque o Controle de Aplicativo do Windows já
   bloqueou o executável gerado pelo uv (ver `frontend/CONCEITO.md`). Se o NSSM também for
   bloqueado, o plano B é o **Agendador de Tarefas**: uma tarefa "Ao iniciar o sistema", executando
   mesmo sem usuário logado, que chama um `.cmd` com os dois comandos.
4. Liberar **só a porta 3000** no firewall, e só na rede privada/domínio:
   `New-NetFirewallRule -DisplayName "Solufarma" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow -Profile Private,Domain`.
   A 8000 fica fechada (a API escuta em `127.0.0.1`).
5. Atualizar versão: `git pull`, `npm run build`, reiniciar os dois serviços (`nssm restart ...`).

**O que muda no código:** nada obrigatório. Opcional (M): gravar os envios numa tabela do
Supabase para a lista da tela "Enviar" sobreviver a reinícios.

**Custo:** US$ 0 de hospedagem se já existe um PC que fica ligado; só a energia. Um mini-PC novo
para isso custa uma vez só (compra, não mensalidade).

**Riscos**
- Segurança sem login: qualquer pessoa na **rede do escritório** (inclusive o Wi-Fi de visitantes,
  se não for separado) consegue usar. Aceitável para uso interno; conferir se o Wi-Fi de visitas é
  isolado.
- Tráfego em HTTP sem criptografia dentro da rede local. Baixo risco num escritório pequeno.
- Disponibilidade: depende do PC. Queda de energia, atualização do Windows que reinicia ou alguém
  que desliga a máquina derrubam o sistema (os serviços voltam sozinhos quando o PC religa).
- Acesso de fora do escritório: não existe. Se alguém precisar em home office, a saída sem expor
  nada é uma VPN simples (ex.: Tailscale) instalada no PC servidor e no notebook da pessoa.

**Esforço:** P (meio dia a um dia, incluindo testar a partir de outro computador).

---

## Opção B: Vercel (frontend) + host de container para a API

O Next vai para a Vercel; a API vai para um serviço que roda container sempre ligado (Render,
Railway ou Fly.io). Endereço público, acessível de qualquer lugar.

**O problema central:** sem login, um endereço público entrega o acervo e o cartão de crédito do
LLM a quem descobrir a URL. Aqui há **duas** portas para trancar: o site na Vercel e a URL pública
da API (a Vercel precisa alcançá-la pela internet).

**Travas que cada plataforma oferece (30/09/2026)**

| Plataforma | Trava disponível | Serve? |
|---|---|---|
| Vercel Hobby (grátis) | Uso **não comercial** apenas; sem proteção por senha | Não serve para a empresa |
| Vercel Pro (US$ 20/mês, 1 assento de desenvolvedor) | **Vercel Authentication** em "All Deployments": grátis; só entra quem tem conta Vercel e está no time. Assentos "Viewer" são gratuitos, então cada pessoa da equipe cria uma conta Vercel e é convidada como Viewer | Sim, é o "login" que dá para ter sem escrever código |
| Vercel Pro + Password Protection | Senha única para o site: **+US$ 20/mês por projeto** | Sim, mais simples para a equipe |
| Vercel Trusted IPs (allowlist de IP) | Só no plano Enterprise | Não |
| Render: Inbound IP rules | Só nos planos Scale/Enterprise para web services | Não, no nosso porte |
| Render/Railway/Fly: Basic Auth | Não há recurso pronto; teria de ser feito na própria API | Via código |

**Consequência:** a URL da API fica pública em qualquer desses hosts, então a API precisa exigir
uma chave própria (um segredo que só o Next conhece). O `rewrite` do `next.config.ts` não
acrescenta cabeçalho à requisição, então isso exige trocar o rewrite por uma rota do Next que
repassa a chamada com o segredo. Na Vercel essa rota é uma Function, com **limite de 4,5 MB no
corpo da requisição**: o upload de PDF de até 50 MB deixa de passar pelo Next e precisa ir direto
ao Supabase Storage por URL assinada de upload, com a API disparando o pipeline depois. Além
disso, requisições repassadas pela Vercel a um endereço externo têm teto de 120 s: uma pergunta
lenta ao agente pode estourar.

**Onde pôr a API (sempre ligada, com ≥ 2 GB de RAM)**

| Host | Plano que aguenta | Custo/mês | Observação |
|---|---|---|---|
| Render | Standard (2 GB) | US$ 25 (+ disco US$ 0,25/GB se quiser persistente) | Starter (US$ 7, 512 MB) não aguenta o OCR. Sem região no Brasil |
| Railway | Hobby US$ 5 + uso (US$ 10/GB RAM, US$ 20/vCPU por mês) | ~US$ 20–30 com 2 GB sempre ligada | Cobra pelo consumido; volume US$ 0,15/GB |
| Fly.io | shared-cpu-1x 2 GB em `gru` (São Paulo) | ~US$ 9–10 + volume US$ 0,15/GB | Tem região em São Paulo (perto do Supabase). Desligar o `auto_stop_machines`, senão a máquina para no meio do OCR |

**Passos**
1. Escrever um `Dockerfile` para a API (Python 3.11, `uv sync`, `pip install -r api/requirements.txt`,
   `python -m uvicorn ... --host 0.0.0.0`).
2. Subir no host escolhido, com as chaves do `.env` como variáveis secretas da plataforma.
3. Implementar o segredo Next→API, o upload direto para o Storage e (recomendado) os envios numa
   tabela, porque esses hosts reiniciam o container a cada deploy.
4. Criar o projeto na Vercel (plano Pro), `API_URL` apontando para a API, ativar Vercel
   Authentication em "All Deployments" e convidar a equipe como Viewer (ou pagar a senha).

**O que muda no código:** Dockerfile; rota de proxy com segredo no lugar do rewrite; checagem do
segredo na API; upload direto ao Storage; estado dos envios em tabela. É a opção que mais mexe.

**Custo:** US$ 20 (Vercel Pro) + US$ 10 a 25 (API) = **~US$ 30–45/mês**; +US$ 20 se usar senha
em vez de contas Vercel.

**Riscos:** duas plataformas para manter e pagar; a API pública depende de o segredo nunca vazar;
cada pessoa da equipe precisa de conta Vercel (ou todos dividem uma senha); teto de 120 s por
pergunta; limite de corpo no upload.

**Esforço:** G (3 a 5 dias, contando as mudanças de upload e os testes).

---

## Opção C: tudo numa VM pequena, com Caddy + HTTPS + Basic Auth

Uma máquina virtual Linux roda a API e o Next exatamente como no PC local. Na frente, o Caddy
(servidor web) emite o certificado HTTPS sozinho e pede usuário e senha antes de qualquer página
ou chamada `/api`. É a opção A, só que na nuvem e acessível de qualquer lugar.

**Passos**
1. Criar a VM (sugestão: **AWS Lightsail em São Paulo, 2 GB, US$ 12/mês**, na mesma região da AWS
   em que está o Supabase). Ubuntu LTS. No firewall da Lightsail, abrir só 80, 443 e 22 (SSH,
   de preferência restrito ao IP do escritório).
2. Apontar um domínio (ex.: `assistente.solufarma.com.br`) para o IP fixo da VM.
3. Instalar `uv`, Node e Caddy; clonar o repositório; copiar o `.env` (`chmod 600`);
   `npm ci && npm run build`.
4. Criar dois serviços `systemd` (API em `127.0.0.1:8000`, Next em `127.0.0.1:3000`), com
   `Restart=always`.
5. `Caddyfile`:
   ```
   assistente.solufarma.com.br {
       basic_auth {
           equipe <hash gerado com: caddy hash-password>
       }
       reverse_proxy 127.0.0.1:3000
   }
   ```
   Pode ter um usuário por pessoa (várias linhas em `basic_auth`), o que permite tirar o acesso
   de alguém sem trocar a senha de todos.
6. Atualizar versão: `git pull`, `npm run build`, `systemctl restart` nos dois serviços.

**O que muda no código:** nada obrigatório (o disco da VM é persistente, o processo fica sempre
ligado, upload de 50 MB passa normalmente; o Caddy não tem o teto de 120 s da Vercel). Opcional
(M): envios em tabela.

**Custo (VM de 2 GB ou mais)**
- AWS Lightsail São Paulo, 2 GB / 2 vCPU / 60 GB: **US$ 12/mês** (mesmo preço dos EUA; em São Paulo
  a franquia de tráfego é a metade, 1,5 TB, que sobra).
- Hetzner CX23, 4 GB / 2 vCPU / 40 GB, na Alemanha/Finlândia: **€ 5,49/mês** (~US$ 6,50). Mais
  barata, mas longe do Supabase (cada consulta ao banco atravessa o Atlântico).
- DigitalOcean, 2 GB / 1 vCPU: US$ 12/mês, sem região no Brasil.
- Domínio `.com.br`: ~R$ 40/ano no Registro.br (ou um subdomínio do site que a Solufarma já tem,
  custo zero).

**Riscos**
- Segurança sem login: a Basic Auth é uma senha na porta. Boa o bastante para 5 a 15 pessoas,
  desde que a senha não circule fora da equipe. Não há registro de "quem perguntou o quê".
- Alguém precisa aplicar atualizações do Ubuntu de vez em quando (dá para ligar as
  atualizações automáticas de segurança).
- Disponibilidade: boa (datacenter), sem depender de PC do escritório.

**Esforço:** M (1 a 2 dias, incluindo DNS e HTTPS).

---

## Comparação rápida

| | A. PC interno | B. Vercel + container | C. VM + Caddy |
|---|---|---|---|
| Custo de hospedagem/mês | US$ 0 | ~US$ 30–45 (+20 com senha) | US$ 12 (Lightsail SP) ou ~US$ 6,50 (Hetzner) |
| Acesso de fora do escritório | Não (só com VPN) | Sim | Sim |
| Exposição do acervo e do LLM | Só rede interna | Pública, duas portas para trancar | Pública, uma porta com senha |
| Mudança de código | Nenhuma | Várias (proxy com segredo, upload, Dockerfile) | Nenhuma |
| Esforço | P | G | M |
| Depende de | Um PC sempre ligado | Duas contas pagas | Um domínio e alguém que cuide da VM |

## Recomendação

**Comece pela A** se a equipe usa o assistente no escritório, que é o caso descrito no
`CONCEITO.md` (desktop, uso interno). Custa zero, não exige nenhuma mudança de código, não expõe
nada na internet e fica pronta em um dia.

**Vá para a C** se houver necessidade real de acesso fora do escritório ou se não houver um PC
confiável para ficar ligado: Lightsail em São Paulo com Caddy e Basic Auth, US$ 12/mês, sem
mudar código. Passar de A para C depois é só repetir os mesmos passos numa VM.

**Não recomendo a B agora.** É a mais cara, a que mais mexe no código e, mesmo assim, deixa a API
pública dependendo de um segredo. Só faz sentido se o login (F8) voltar ao plano e a empresa
quiser a Vercel por outros motivos.

Em qualquer opção: limite de gasto na chave do OpenRouter antes de ligar `MODO_DEMO=0` para a
equipe.

## O que o Roger precisa decidir ou fornecer

1. **A equipe precisa acessar de fora do escritório?** Não → A. Sim → C (ou A + VPN).
2. **Para a A:** qual PC vai ser o servidor (fica ligado, ≥ 8 GB de RAM) e quem da TI/rede
   reserva um IP fixo e confirma que o Wi-Fi de visitantes é separado.
3. **Para a C:** quem paga a conta da AWS (cartão da empresa) e qual domínio/subdomínio usar.
   Uma senha por pessoa ou uma senha única da equipe.
4. **Teto de gasto mensal com LLM/OCR** para configurar o limite da chave do OpenRouter.
5. Se o gerente aceita "senha na porta" (C) como substituto do login, ou se um endereço
   público exige o login de verdade (reabre a F8).

---

### Fontes (consultadas em 30/09/2026)

- Vercel, preços e Deployment Protection: <https://vercel.com/pricing>,
  <https://vercel.com/docs/deployment-protection>,
  <https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication>
  (Pro US$ 20/mês; Password Protection US$ 20/projeto/mês; Trusted IPs só Enterprise; Hobby é
  não comercial). Assentos Viewer gratuitos no Pro: <https://vercel.com/docs/plans/pro-plan>.
- Vercel, teto de 120 s em rewrite externo e 4,5 MB de corpo em Functions:
  <https://vercel.com/docs/limits>, <https://vercel.com/docs/functions/limitations>.
- Render: <https://render.com/pricing> (Starter US$ 7, Standard US$ 25, disco US$ 0,25/GB);
  IP rules só Scale/Enterprise: <https://render.com/docs/inbound-ip-rules>.
- Railway: <https://railway.com/pricing> (Hobby US$ 5; RAM US$ 10/GB; vCPU US$ 20; volume US$ 0,15/GB).
- Fly.io: <https://docs.fly.io/about/pricing/> (shared-cpu-1x 2 GB até ~US$ 9,36/mês; `gru` com
  multiplicador 1,615; volume US$ 0,15/GB).
- AWS Lightsail: <https://aws.amazon.com/lightsail/pricing/> (US$ 12: 2 GB / 2 vCPU / 60 GB; São
  Paulo com metade da franquia de tráfego).
- Hetzner: <https://www.hetzner.com/cloud> e calculadora <https://costgoat.com/pricing/hetzner>
  (dados de 05/09/2026: CX23 € 5,49 na UE, após o reajuste de 2026).
- DigitalOcean: <https://www.digitalocean.com/pricing/droplets> (2 GB US$ 12; sem região no Brasil).
