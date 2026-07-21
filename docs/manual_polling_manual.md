# Manual do Polling Manual

Da fila de relatórios até a pesquisa salva nas matrizes T1 e T2.

Última revisão: 21/07/2026.

---

## O caminho em 7 passos

1. Abrir a fila e filtrar o que está pendente
2. Abrir o material (link ou PDF do Drive)
3. Levar o conteúdo pro Polling Manual (colar texto ou subir o PDF)
4. Refinar o foco, se o material tiver mais de uma pesquisa
5. Extrair com o Gemini
6. Conferir "Dados extraídos" e cada cenário
7. Salvar

Tempo médio por pesquisa: 5 a 10 minutos. PDF de instituto grande com muitos cenários: 20 a 30.

---

## Passo 1. Ver o que ficou pendente

Planilha **Eleições 2026 - Fluxo de Pesquisa e Coleta dos Dados**, aba **`relatorios`**.

Filtre a coluna **`Voto cadastrado?`** por **`⚠️ REGISTRE NO POLLING MANUAL`**. Essas são as linhas que o robô não consegue fechar sozinho e que esperam lançamento manual.

Uma linha = um **Registro TSE + Cargo**. A mesma pesquisa aparece em duas linhas quando cobre governador e senador.

O que cada coluna quer dizer antes de você começar:

| Coluna | Valor | O que fazer |
|---|---|---|
| `Situação da fonte` | `ok` | Tem link conferido, pode lançar |
| | `suspensa` | Pesquisa suspensa pela Justiça. **Não lance.** Fica N/A |
| | `fora_da_janela` | Fora do período de interesse. Não lance |
| | vazio | Fonte ainda não foi buscada. Espere o robô ou busque na mão |
| `Conferido?` | `sim` | O link foi validado contra o registro TSE |
| `Segmentos extraídos?` | `sim`/`não` | Independente do seu trabalho. `não` = o relatório só tem resultado geral |
| `Voto cadastrado?` | `⚠️ REGISTRE NO POLLING MANUAL` | **É a sua fila** |
| | `sim` | Já lançado, não mexa |
| | `N/A` | Suspensa ou fora da janela |

O material está em **`Link na internet`** (notícia ou página do instituto) ou em **`PDF salvo no Drive`** (snapshot congelado). Prefira o PDF do instituto quando existir: notícia costuma trazer só um cenário.

---

## Passo 2. Abrir o material e decidir a rota

Duas rotas, escolha pelo tipo de material:

**Rota A — texto.** Notícia, release, página do instituto. Copie o texto inteiro e cole no campo grande "Texto completo da notícia / PDF OCR".

**Rota B — PDF.** Relatório do instituto. Use o expander "Extrair texto de PDF".

Regra prática: se o material tem tabela ou gráfico, vá de PDF. Texto colado de notícia perde número.

---

## Passo 3. Ler o PDF (modo de leitura)

No expander "Extrair texto de PDF", depois do upload aparecem três controles.

**Modo de leitura:**

| Modo | Quando usar |
|---|---|
| `Auto (texto se tiver; imagem se for scan)` | Padrão. Tenta texto e cai pra imagem se vier pouca coisa (< 800 caracteres) |
| `Texto (PyMuPDF)` | PDF nativo, tabela limpa. Mais rápido e barato |
| `Imagem (Gemini visão)` | PDF escaneado, ou gráfico de barra, ou quando o texto veio picado |

**Página inicial / final:** sempre recorte. Não jogue um PDF de 120 páginas inteiro.

> **Armadilha de gráfico de barra.** Quando o nome do candidato está em rótulo rotacionado no eixo X, o modo Texto perde os nomes e deixa só os números soltos. Aconteceu de verdade com o PDF do Instituto França (DF-04765/2026). Solução: selecione **só as páginas que interessam** e use `Imagem (Gemini visão)`. Se você mandar o PDF inteiro no Auto, o total de texto passa do limiar, o Auto escolhe modo texto, e vem número sem nome.

Depois de "Ler PDF para texto bruto", o texto cai no campo principal. **Olhe o texto** antes de extrair: se estiver com números soltos sem nome, troque o modo e leia de novo.

---

## Passo 4. Link da fonte (obrigatório)

Campo "Link da notícia ou relatório". Precisa começar com `http`. Sem ele o salvamento é bloqueado.

Vai pras colunas `fonte_url` e `fonte_url_original` das duas matrizes. Uma extração = um material = um link, valendo pra todos os cenários.

---

## Passo 5. Refinar extração (opcional, mas resolve muita coisa)

Expander "Refinar extração". Use quando o material tem mais coisa do que você quer lançar.

- **Cargo-alvo / UF-alvo / Turno-alvo / Instituto-alvo:** restringe o que o Gemini pode extrair.
- **Instruções adicionais:** texto livre. Ex.: "Pegar só o cenário sem o Ratinho Junior", "Usar o segundo bloco da página 3".

> **PDF com 1º e 2º turno junto tem que ser processado duas vezes.** Relatório majoritariamente T1 que traz um confronto de 2º turno escondido (às vezes rotulado só como "RESULTADO GERAL") não sai numa passada só. Rode uma vez com Turno-alvo `t1`, salve, limpe a tela, e rode de novo com Turno-alvo `t2`.

Se você definiu foco e o Gemini não achou nada que case, ele avisa e não carrega nada. Ajuste o foco ou volte pro material.

---

## Passo 6. Conferir "Dados extraídos"

Esse bloco vale pra **pesquisa inteira**. Cargo, turno, UF e registro TSE **não** ficam aqui, ficam em cada cenário.

### Instituto

Selectbox alimentado pelo catálogo canônico das matrizes T1 e T2.

- Se aparecer **"⚠️ Confira a grafia: este nome não está no catálogo canônico"**, pare. O app sugere correspondências. Escolha a sugestão.
- Nome fora do catálogo cria um instituto novo nas matrizes e **parte a série histórica em duas**. O painel passa a mostrar "Instituto Paraná" e "Instituto Paraná de Pesquisas" como coisas diferentes.
- A metodologia não é digitada: vem do cadastro central do instituto.

### Data do campo — a armadilha mais cara

O campo pede **`YYYY-MM-DD`**. Digite exatamente assim.

O normalizador aceita `YYYY-MM-DD` e `M/D/YYYY` (**padrão americano, mês primeiro**). Ele **não** entende `DD/MM/YYYY`.

- `2026-07-01` → certo.
- `01/07/2026` (1º de julho, jeito brasileiro) → lido como **7 de janeiro**. Grava `2026-01-07` sem reclamar.
- `14/07/2026` → mês 14 não existe, então fica o texto cru na planilha e quebra o `ano`.

Por que importa tanto: `data_campo` entra no **`poll_id`**. Data errada = pesquisa com identidade errada, que não é pega pelo detector de duplicata e vira uma série paralela no painel. O `ano` também sai daqui (primeiros 4 caracteres).

> Outra armadilha de data já vista ao vivo: o Gemini pegava o ano da **Resolução-TSE** citada no rodapé ("23.600/2019") e gravava 2019 numa pesquisa de 2026. Já foi corrigido no prompt, mas **confira o ano** sempre.

### Amostra, margem de erro, confiança

- Confiança: inteiro entre 1 e 100. `95`, não `95,0`. Fora disso, bloqueia o salvamento.
- Margem: aceita decimal (`3.2`).
- Os dois normalmente estão na mesma frase da ficha técnica.

### Modo de coleta

Selectbox. Se o material disser algo que não está na lista, escolha "Outro" e digite.

### Observações

Texto livre, não vai pras matrizes. Use pra registrar o que te deu dúvida.

### Avisos que aparecem aqui

- **"estes partidos não vieram da pesquisa, foram puxados da nossa base"**: o app completou partido pela base T1/T2. Confira nome por nome, partido troca.
- Pendências da extração: cada uma é um ponto que o Gemini não conseguiu resolver.

---

## Passo 7. Conferir cada cenário

Os cenários vêm agrupados por **Cargo — Turno**. Cada cenário tem:

### Cargo, Turno, UF

Por cenário, de propósito. Relatório estadual traz presidente + governador + senador junto, e presidente às vezes é pesquisado só num estado.

- **UF:** `BR` para presidente nacional. Se o relatório mediu presidente só na Bahia, o cenário de presidente vai com `BA`.
- **Turno:** `senador nunca tem 2º turno`. Se um cenário de senador vier marcado `t2`, está errado.
- Para presidente e governador, 2 candidatos numa tabela é sinal de 2º turno, e a extração infere assim.

### Registro TSE

Pré-preenchido, resolvido por cargo: quando o texto traz dois registros (`DF-04765/2026, BR-06776/2026`), o `BR-` vai pro presidente e o outro pro cargo estadual. Quando é ambíguo, o campo mostra os dois juntos e **você tem que cortar na mão**.

> **O app não valida o formato do registro.** Qualquer texto não-vazio passa. Um registro com dígito trocado é aceito, entra no `poll_id`, escapa do detector de duplicata e não bate com a linha da fila (o app avisa "não achei linha na fila de relatórios pra..."). **Confira caractere por caractere contra o PDF.**

Obrigatório em qualquer pesquisa de 2026. Cenário com resultado e sem registro bloqueia o salvamento.

### Número do cenário (só T1)

É o número que vai pro `scenario_label` da matriz. Default = posição dentro do grupo cargo+turno.

Se o relatório tem cenário estimulado com 5 nomes e outro com 8, são os cenários 1 e 2 daquele cargo. Não use o número global do documento.

### Tabela de candidatos

Quatro colunas:

| Coluna | Regra |
|---|---|
| `candidato` | Nome como no material. É normalizado depois |
| `partido` | Sigla. Vazio gera aviso, não bloqueia |
| `percentual` | Uma casa decimal. `41,49` vira `41.5` (arredonda, não trunca) |
| `tipo` | `candidato` ou `nao_valido` |

**`tipo` é o campo que mais quebra coisa.** Branco, nulo, indeciso, "não sabe", "nenhum" têm que ser `nao_valido`. O app tenta classificar sozinho pelo nome, mas confira.

Por quê: no T2 a validação exige **exatamente 2 candidatos válidos**. Se "Branco/Nulo" ficou marcado como `candidato`, viram 3 e o salvamento é recusado. E a `disputa` do T2 (`t2_lima-lula`) é montada a partir desses dois nomes.

---

## Passo 8. Salvar

### Antes de clicar

Checkbox **"Marcar esta pesquisa como concluída na fila"**, marcado por padrão.

**Desmarque** se ainda faltam cenários deste mesmo Registro TSE + Cargo pra lançar depois. O eixo-eleicoes nunca revisita uma linha marcada `sim` — se marcar cedo demais, a pendência some da fila e ninguém volta nela.

### Alerta de duplicata

Se aparecer, leia a tabela. Ela mostra o motivo, o `poll_id` e a origem da linha que já existe.

- Mesma pesquisa → "Cancelar e revisar".
- Pesquisa diferente de verdade (raro) → "Salvar mesmo assim".

Duplicata quase sempre significa que alguém já lançou, ou que a data/registro está diferente do que já foi gravado.

### O que acontece ao salvar

1. Cenários T1 vão pra **Matriz T1**, cenários T2 vão pra **Matriz T2**. Um material com os dois grava nas duas de uma vez.
2. Cada cenário vira 1 linha em `pesquisas` e N linhas em `resultados`.
3. A linha da fila é marcada `sim` + data (se o checkbox estiver marcado).
4. A média móvel de 13 dias **não** atualiza na hora. Um workflow reconstrói `resultados_bi` de 4 em 4 horas. O painel só muda depois disso.

### Depois de salvar

Clique **"🧹 Limpar tudo"** na sidebar antes da próxima pesquisa. Zera texto, link, foco, header e cenários. Sem isso, resíduo da pesquisa anterior pode vazar pra próxima.

---

## Checklist crítico

Os 5 campos que estragam a matriz se estiverem errados:

1. **Data do campo** em `YYYY-MM-DD`. Confira o ano contra o PDF, nunca contra a Resolução-TSE citada.
2. **Registro TSE** conferido caractere por caractere. O app não valida formato.
3. **Instituto** escolhido do catálogo, sem aviso de grafia.
4. **`tipo` = `nao_valido`** em branco, nulo, indeciso e NS/NR.
5. **Turno** certo por cenário. Senador nunca é t2.

E dois que estragam o gráfico sem quebrar nada:

6. **Partido** preenchido em todo candidato de verdade. `Lula (PT)` e `Lula` viram duas séries no painel.
7. **UF** do cenário. Presidente medido só num estado vai com a UF do estado, não `BR`.

---

## Erros que o app mostra

| Mensagem | Causa | O que fazer |
|---|---|---|
| "Registro TSE é obrigatório para pesquisas de 2026" | Algum cenário com resultado ficou sem registro | Preencha o registro daquele cenário |
| "T2 exige exatamente dois candidatos válidos; encontrei N" | Branco/nulo marcado como `candidato`, ou falta um nome | Corrija a coluna `tipo` |
| "Cenário N: duplicado após a padronização" | Dois cenários do mesmo cargo/turno com o mesmo número | Renumere |
| "Cole o link da notícia ou relatório" | Campo de link vazio | Cole a URL |
| "Confiança deve ser um percentual inteiro entre 1 e 100" | Digitou `95,0` ou texto | Digite `95` |
| "Falta configurar o ID da Matriz T1/T2" | Secret ausente no Streamlit Cloud | Chame quem administra o app |
| "não achei linha na fila de relatórios pra X (cargo)" | Registro ou cargo não bate com nenhuma linha da fila | Confira o registro; a pesquisa **foi salva**, só a fila não fechou |
| "Não foi possível concluir a leitura do PDF" | Intervalo grande demais ou PDF problemático | Reduza as páginas ou troque o modo |

---

## Quando não lançar

- `Situação da fonte` = `suspensa`. Pesquisa suspensa pela Justiça Eleitoral não entra na matriz.
- `Situação da fonte` = `fora_da_janela`.
- Link que não bate com o registro TSE da linha. Isso é dado errado na fila, não é pra corrigir no Polling Manual.
- PDF que você não conseguiu ler direito. Número sem nome de candidato, ou percentual que soma muito acima de 100, é sinal de leitura ruim. Melhor deixar pendente do que gravar errado.
