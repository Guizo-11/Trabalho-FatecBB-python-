Moonrise

Leitor de mangás, manhwas e webtoons feito em Python, com Flask e banco de dados SQLite.
O administrador publica as obras e os capítulos (imagens), e os leitores pesquisam, leem, favoritam e dão nota.

Como rodar

Requisito: Python 3.10 ou mais novo.



A primeira conta criada em "Criar conta" vira a conta de administrador.

Bibliotecas usadas

Nenhuma biblioteca além do Flask é necessária. O visual usa só HTML, CSS e um pouco de JavaScript (carrossel), todos dentro da pasta `static/`, então o site funciona sem internet.

1 Rode `python app.py` e abra http://127.0.0.1:5000
2 Clique em "Criar conta": a primeira conta vira administradora.
3 Entre em `/admin`, clique em "Nova obra" e crie uma obra com capa.
4 Abra a obra no painel e publique um capítulo enviando várias imagens.
5 Saia, crie uma segunda conta (leitor) e teste busca, leitura, favorito e nota.

O que o site faz

Leitores
 Página inicial com carrossel de destaques, "Continuar lendo", "Mais lidas nos últimos 7 dias", "Capítulos novos" e catálogo
 Busca por título, autor ou gênero, com filtro por tipo (Mangá, Manhwa, Manhua, Webtoon, HQ) e ordem
 Página da obra com capa, gêneros, sinopse, nota média, visualizações e lista de capítulos (marca os já lidos)
 Leitor com as páginas em rolagem, troca de capítulo e botões de anterior e próximo

Contas
 Cadastro e login (com usuário ou e-mail); a senha é salva criptografada
 Favoritos, nota de 1 a 10 e "continuar de onde parou"
 Página "Minha conta" com resumo de leitura e troca de senha

Administrador
 Painel com números do site (obras, capítulos, contas, leituras da semana)
 Criar, editar e excluir obras, com capa e opção de aparecer no carrossel
 Publicar capítulos enviando várias imagens de uma vez (a ordem segue o nome dos arquivos)
 Gerenciar usuários: tornar admin, remover admin e excluir conta

Estrutura


app.py              lógica do site: rotas, banco de dados e login
templates/          o HTML de cada página
  admin/            páginas do administrador
static/
  estilo.css        visual do site (cores no começo do arquivo)
  script.js         carrossel e menu do topo
  logo.png, lua.png logo da Moonrise Scans
  fontes/           fontes Adventor e Inter (licenças em LICENCAS.txt)
  uploads/          capas e páginas enviadas (criada sozinha)
moonrise.db         banco de dados (criado sozinho na primeira execução)


Banco de dados

| Tabela | Guarda |
| usuario | contas, senha criptografada e se é admin |
| obra | título, autor, tipo, situação, gêneros, sinopse, capa |
| capitulo | número e título de cada capítulo |
| pagina | as imagens de cada capítulo, em ordem |
| favorito | quem favoritou qual obra |
| avaliacao | a nota que cada pessoa deu |
| leitura | cada capítulo aberto (visualizações e "continuar lendo") |

A view `obra_info` junta cada obra com a nota média, as visualizações e o último capítulo.
