# Diretrizes de Correção — Lab 03 FilmNow

---

## Funcionalidade Básica — peso 10

O programa funciona para a descrição presente na especificação do lab.

São funcionalidades esperadas para o sistema (2,5 pontos cada uma):

- **Adicionar Filme** (2,5)
- **Mostrar Filmes** (2,5)
- **Detalhar Filme** (2,5)
- **HotList** (2,5): Exibir HotList, Atribuir Hot, Remover Hot

Cada funcionalidade pode estar:
- completa ou quase completamente correta → **2,5**
- com falhas consideráveis → **1,5**
- não feita ou praticamente nada feito → **0,0**

> **Atenção:** não penalizar de forma duplicada. Ex.: se na adição de filme for observada a ausência de algum dado de entrada, como o ano, ao avaliar o "detalhar filme" não deve ser penalizado o fato de ele não mostrar o ano.

---

## Criação das Classes — peso 10

- **4 pts** — Classe `Filme` ou equivalente: a representação de Filme pode ter variações sobre a representação de ano. Pode ser usado `String` ou `int`.
- **5 pts** — Classe `FilmNow` ou equivalente: lembrar que `FilmNow` tem composição com `Filme`.
- **1 pt** — Classe de interface com usuário que contém o `main`. O principal ponto aqui é que o aluno modularize o `main` com métodos estáticos, evitando a presença de métodos grandes.

---

## Uso de Referências — peso 10

- **7 pts** — Usou estático apenas no `main` ou em constantes.
- **3 pts** — Cria objetos de forma adequada (`FilmNow`, `Filme`).

---

## Uso de Array/Coleção — peso 10

- **10 pts** — Uso correto da estrutura de dados (array ou outra coleção).

Permitimos que os alunos explorassem as coleções de Java caso desejassem. Ou seja, o lab conduz ao uso de arrays, mas o uso de coleções de Java não deve ser penalizado a menos que o uso esteja incorreto ou que as restrições impostas no lab sobre o armazenamento dos dados não sejam obedecidas. Por exemplo, `FilmNow` só pode ter 100 filmes; se isso não for obedecido no uso de um `ArrayList`, então deve ser penalizado.

- **-1 pt** — Começou da posição 1 do array (índice 0 ignorado).

---

## Testes — peso 10

- **4 pts** — Testes da classe `Filme` (1 pt por grupo):
  - Testes de Construtor
  - Testes de Exibir/toString (com e sem alguns dados)
  - Testes de pegar dados (ex.: versão completa, versão resumida)
  - Testes de `equals` e outros métodos específicos do design do aluno

- **6 pts** — Testes da classe `FilmNow` (2 pts por grupo):
  - Testes de adição de Filme (válido, posições limite, filmes já adicionados, sobrescrita de filme)
  - Testes de listagem/exibição de filme (listar vazio, detalhar filme, posição inválida)
  - Testes de HotList (adicionar hot, remover hot, detalhar filme hot, exibir filme ex-hot, exibir hotlist)

---

## Divisão de Funcionalidades — peso 10

- **3 pts** — O `Main` (e/ou menu) responsável por entrada e saída. Não pedimos a criação de uma classe Menu, mas observamos que muitos alunos seguiram por esse lado. O que esperamos basicamente é que ele tenha separado toda a parte de interação com o usuário da lógica do sistema (`FilmNow`/`Filme`).
- **5 pts** — `FilmNow` é responsável por criar, adicionar e gerenciar os filmes.
- **2 pts** — O `Filme` é responsável por definir a exibição de seus detalhes em lista e no "Mostrar todos".

---

## Legibilidade e Documentação — peso 10

Não é necessário documentar componentes privados da classe, seja atributos ou métodos.

- **6 pts** — Código e documentação seguem o estilo Java e estilo Javadoc.
- **4 pts** — Documentação ser clara e objetiva, e mostrar aspectos além de código/nome.
  - Exemplo de **má** documentação: `getDetalhesFilme` — Retorna nome do filme.
  - Exemplo de **boa** documentação: `getDetalhesFilme` — Retorna detalhes do filme, incluindo nome, ano e local de exibição.


