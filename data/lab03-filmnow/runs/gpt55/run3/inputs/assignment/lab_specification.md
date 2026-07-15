# Laboratório 03 — FilmNow: A sua lista de filmes e séries

---

## Como usar esse guia

- Leia atentamente cada etapa.
- Quadros com dicas têm leitura opcional; use-os conforme achar necessário.
- Preste atenção nos trechos marcados como importante (ou com uma exclamação).

---

## Conteúdo sendo exercitado

- Classe básica de composição
- Uso do `equals`
- Introdução a testes de unidade com JUnit
- Introdução a tratamento de erros com exceção

## Objetivos de aprendizagem

Ao final desse lab você deve conseguir:

- Reconhecer composição na relação entre objetos em código Java
- Usar delegação para implementar composição entre objetos
- Implementar métodos de igualdade entre objetos (`equals` em Java)
- Criar testes para programas que lhe ajudem a confiar na sua implementação e a ganhar tempo quando estiver programando
- Usar exceções para tratar situações inesperadas em programas

## Perguntas que você deveria saber responder após este lab

- Como se caracteriza o relacionamento entre objetos via composição?
- O que significa dizer que o método `equals` é um método padrão de Java?
- Em que situações é necessário sobrescrever o método `equals`?
- O que é uma exceção?
- De que forma podemos usar exceções para lidar com entradas inválidas?
- Toda exceção deve fazer o programa parar?
- Os testes de unidade devem testar a unidade básica de um programa em Java. Liste algumas boas práticas para escrever testes de unidade.
- Em um cenário de composição, como separamos os testes da classe base (composite) e da classe composta?

---

## FilmNow — A sua lista de filmes e séries

> "Eu consigo arranjar um tempinho em minha rotina para assistir um filme, mas gasto esse tempo escolhendo o filme." Quem nunca? É para resolver esse problema que surgiu o FilmNow. Um sistema em que você guarda indicações de filmes e séries para que você possa assisti-los quando tiver tempo!

No FilmNow você pode adicionar e visualizar filmes. Um filme é representado por um **nome**, **ano de lançamento** e o **local** através do qual você pode assisti-lo (Netflix, Prime Vídeo, Cinema, etc). Você poderá listar todos os filmes, exibindo o nome e ano de lançamento, bem como a sua posição na lista. Deverá ser possível, também, obter detalhes de um filme específico (a partir da posição do filme na lista).

No FilmNow, além da listagem há também a funcionalidade de adição de filmes. Para adicionar um filme, às suas características mencionadas anteriormente devem ser informadas, bem como a posição que ele deverá ser inserido na lista. O sistema está **limitado em 100 filmes**.

---

> **Dica — O que fazer nas situações que NÃO ESTÃO especificadas?**
>
> **Resposta: Se não foi especificado, não precisa fazer. Faça o mais simples.**
>
> Quando não está especificado o que fazer, você é livre para fazer o que quiser. A dica que podemos dar é… não implemente. Ser preguiçoso tem sua vantagem. Imagine que você está desenvolvendo o Sistema de Filmes para um cliente, e você colocou o diretor como uma característica do filme no sistema. Três coisas podem acontecer:
> - O cliente não gostou da ideia, e você terá perdido tempo programando o campo diretor;
> - O cliente gostou da ideia, mas quer que você faça de um jeito diferente considerando, agora, todo o elenco, por exemplo;
> - O cliente gostou da ideia e gostou do jeito que você fez.
>
> A última alternativa é praticamente impossível de acontecer… As outras duas implicam em retrabalho. Caso você acabe o projeto antes, dedique seu tempo a: testar, melhorar a qualidade do código e documentar o que foi feito.

---

Neste laboratório você partirá do código de um colega que *começou a implementação das funcionalidades descritas aqui, mas não acabou*. O código está disponível no repositório GitHub desse Lab. A ideia deste código inicial é facilitar seu desenvolvimento e praticar um pouco a leitura e entendimento de programas. O código contém 3 classes:

- **`FilmNow.java`**: uma versão bem simples de um sistema onde os filmes são, de fato, strings. Você deve modificar essa classe tanto para refletir todas as funcionalidades do FilmNow descritas neste roteiro, quanto para refletir uma representação mais adequada para os filmes. ⚠️ Exemplo: o atributo "ano de lançamento" deve ser alterado para se adequar ao que se espera nessa especificação.
- **`MainFilmNow.java`**: uma versão bem simples de uma interface com usuário para a classe FilmNow. Note que existe um código base bem interessante sobre manipulação de menus aqui. Entretanto, ele está incompleto, especialmente no que se refere às funcionalidades da FilmNow que essa classe irá usar.
- **`LeitorFilmNow.java`**: essa classe lê dados de um arquivo `.csv` que contém dados de filmes. Observe que esse arquivo não contém todas as informações que desejamos para um filme, mas somente dados iniciais como nome, ano e local. O leitor vai carregar esses dados do arquivo e pedir para serem adicionados ao sistema. A ideia é que você não precise mudar nada nessa classe.

---

## 1. Exibir Menu

O sistema deve exibir um menu para o usuário com as opções existentes nesse sistema, como descrito abaixo.

```
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção>
```

Caso o usuário entre com qualquer valor diferente dos possíveis, deve exibir uma mensagem de opção inválida e exibir novamente o menu e o pedido por uma opção, como no exemplo abaixo.

```
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção> X
OPÇÃO INVÁLIDA!
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção>
```

Por fim, a escolha da opção `S` simplesmente encerra a execução do programa.

---

## 2. Adicionar Filme

O FilmNow deve permitir a adição de filmes, como especificado no exemplo abaixo.

```
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção> A

Posição> 1
Nome> Anatomia de uma Queda
Ano> 2023
Local> Cinema
FILME ADICIONADO
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção>
```

⚠️ **Importante!** Caso o usuário selecione uma posição que já exista, o Filme nela existente será substituído.

Fique atento às seguintes situações de erro:

1. O sistema deve permitir apenas posições válidas (entre 1 e 100, inclusive). O sistema deve exibir a mensagem `POSIÇÃO INVÁLIDA` e exibir novamente o menu de opções caso uma posição inválida seja colocada.
2. Caso o usuário tente adicionar um filme com nome e ano de lançamento já existente no sistema, a adição deve ser negada, e a mensagem `FILME JA ADICIONADO` deve ser exibida. Isto deve acontecer mesmo que o usuário tente adicionar o filme em uma posição diferente daquela onde o filme de mesmo nome e ano já está.
3. Caso o usuário tente adicionar um filme com nome vazio, a adição deve ser negada e a mensagem `FILME INVALIDO` deve ser exibida.
4. Caso o usuário tente adicionar um filme com local vazio, a adição deve ser negada e a mensagem `FILME INVALIDO` deve ser exibida.

### Implementando Filme

Existem diferentes formas de estruturar e implementar a entidade Filme no sistema. Na disciplina de programação orientada a objetos você deve pensar em diferentes alternativas que existem entre as diferentes implementações e escolher aquela que seja mais adequada (mais legível, mais fácil de manter, mais barata a curto e longo prazo, etc). Por exemplo, para implementar filmes, você poderia:

- Ter 3 arrays `String[100]`: sendo um para o nome, outro para o ano de lançamento e outro para o local de cada filme;
- Ter uma matriz `String[100][3]`, onde cada linha é um filme e as colunas representam nome, ano e local;
- Ter um `String[300]`, onde para o filme N, a posição `3*N` representa o nome, `3*N+1` ano, `3*N+2` local para cada filme na posição;
- **Criar a classe `Filme`.** Nessa alternativa, a classe de sistema tem um array de filmes (`Filme[100]`) e o Filme passa a ser o responsável por ter o seu próprio nome, ano e demais dados.

⚠️ Cada uma dessas soluções resolve o problema, entretanto, é preciso escolher uma delas e esse é o maior desafio de programar grandes sistemas. De acordo com o conteúdo trabalhado na disciplina até o momento, esperamos que você já leve em consideração os conceitos estudados de orientação a objetos e **opte pela quarta alternativa**.

É importante considerar o método `equals` para `Filme`. Ele permitirá que verifiquemos se dois filmes são iguais. Para tanto, vamos considerar que **dois filmes são iguais se tiverem o mesmo nome e ano de lançamento**. Por exemplo, caso a classe Filme tenha o método `equals`, esse método deveria funcionar como descrito no código abaixo:

```java
Filme filme1 = new Filme("Anatomia de uma Queda", "2023", "Cinema");
Filme filme2 = new Filme("Anatomia de uma Queda", "2023", "Popcornflix");
Filme outroFilme = new Filme("Shrek 2", "2004", "Netflix");

if (filme1.equals(filme2)) {
    System.out.println("O mesmo filme!");
}
if (!filme1.equals(outroFilme)) {
    System.out.println("Não é o filme!");
}
if (!filme1.equals("Donzela")) {
    System.out.println("Filme errado!");
}
```

---

## 3. Detalhar Filme

O sistema permite que sejam exibidos todos os detalhes de um filme específico. Para tanto, deve ser informada a posição em que esse filme foi inserido.

⚠️ Caso seja uma posição fora do limite, deverá exibir a mensagem `POSIÇÃO INVÁLIDA!`. Caso seja uma posição válida e não haja filme na posição, retorne vazio. Em ambos os casos, exiba novamente o menu de opções.

```
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção> D
Posição> 1
Anatomia de uma Queda, 2023
Cinema
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção>
```

### Implementando "Detalhar filme"

Aqui, novamente, você deve escolher entre diferentes possibilidades de implementações:

- O código do `main` usa os atributos do filme para gerar a mensagem a ser impressa;
- O filme tem um método que imprime na saída a mensagem adequada representando o filme;
- O filme tem um método que retorna o que deve ser impresso e o menu imprime o que foi retornado nesse método;
- Uma nova classe será criada. Objetos dessa classe recebem um filme e imprimem a saída desejada.

⚠️ Uma regra boa é não imprimir nada com `System.out` dentro das classes que não são o `main`. Dessa maneira passamos a ter mais flexibilidade uma vez que podemos usar o valor retornado tanto para ser impresso quanto para qualquer outra operação necessária.

---

## 4. Mostrar todos

O FilmNow deverá apresentar toda a sua lista de filmes.

```
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção> M
1 - Anatomia de uma Queda
2 - Pobres Criaturas
11 - Shrek 2
60 - Duna: Parte 2
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(S)Sair
Opção>
```

### Implementando "Mostrar todos"

Todo objeto em Java pode gerar uma representação em String através da implementação do método `public String toString()`. Se sua classe implementa esse método, todo objeto pode ser convertido para String naturalmente pela linguagem Java. Por exemplo, caso a classe Filme tenha o método `toString`, esse método será naturalmente invocado ao realizarmos uma operação como descrita no código abaixo:

```java
Filme novoFilme = new Filme("A Sociedade da Neve", "2023", "Netflix");
System.out.println("Assista esse: " + novoFilme);
// a linha acima é equivalente a:
System.out.println("Assista esse: " + novoFilme.toString());
```

⚠️ Caso não haja filme cadastrado, retorne vazio e exiba novamente o menu de opções.

---

## 5. HotList — os filmes que você precisa assistir!

O FilmNow permite que você crie uma HotList, que representará os filmes ou séries que você está assistindo ou que precisa assistir logo! É uma lista de rápido acesso, **limitada a 10 posições**, dos filmes que você considera "hot" (🔥). É possível atribuir (ou retirar) o status "hot" (🔥) de um filme. A HotList é uma outra forma de acessar seus filmes. Quando você exibe detalhes de um filme que está nessa lista, ele deve ser sinalizado como "hot" (🔥).

Para permitir a manipulação da HotList, devemos implementar as funcionalidades:
- Adicionar Hot
- Exibir HotList
- Remover Hot

Além disso, é preciso alterar a função de "Detalhar filme" para exibir o 🔥 quando esse filme estiver na HotList.

Veja o exemplo abaixo de funcionamento:

```
(A)Adicionar filme
(M)Mostrar todos
(D)Detalhar filme
(E)Exibir HotList
(H)Atribuir Hot
(R)Remover Hot
(S)Sair
Opção> H
Filme> 1
Posicao> 1
ADICIONADO À HOTLIST NA POSIÇÃO 1!

Opção> E
1 - Anatomia de uma Queda, 2023

Opção> D
Filme> 1
🔥 Anatomia de uma Queda, 2023
Cinema

Opção> R
Posicao> 1

Opção> D
Filme> 1
Anatomia de uma Queda, 2023
Cinema
```

Fique atento aos detalhes de uso da HotList:

- Se um novo filme for inserido nessa lista em uma posição que já tenha um filme, o antigo filme deixa de ser um "Hot".
- O filme só pode aparecer uma vez na HotList, ou seja, não é possível incluir um filme que já exista em alguma posição na lista. ⚠️ Nesse caso, exiba a mensagem `FILME JÁ ADICIONADO`.
- ⚠️ Nas operações com a HotList em que for passada posição que não haja filme, informe `POSIÇÃO INVÁLIDA`.

---

## 6. Testar FilmNow

Nosso sistema tem 3 funcionalidades básicas: adicionar, mostrar e detalhar filmes. Para garantir que você implementou o programa corretamente, é preciso garantir que cada uma dessas funcionalidades faça o que foi especificado (validação) e garantir que tudo que o software procura fazer, ele faz corretamente (verificação).

⚠️ Testar o software é uma das maneiras de garantir a sua corretude. Testar um software é verificar se o software a ser executado com determinadas entradas produz a saída esperada. Até agora costumamos sempre receber essas entradas prontas, mas um bom desenvolvedor deve ser capaz de produzir testes adequados para seu programa.

Um bom teste é aquele que:
- É capaz de encontrar erros no programa;
- É simples;
- Não é redundante.

### Casos de teste para "Adicionar Filme" (classe FilmNow)

Para fazer os testes, considere os dados do seguinte filme AVATAR:
- Nome: Avatar
- Ano de Lançamento: 2009
- Local: Disney+

| # | Descrição | Passos | Resultado esperado |
|---|-----------|--------|--------------------|
| 1 | Adicionar um novo filme em posição vazia | Adicionar AVATAR na posição 1 (vazia) | FilmNow deve ter adicionado AVATAR com sucesso. Deve exibir a mensagem `FILME ADICIONADO`. |
| 2 | Adicionar um novo filme em posição existente | Adicionar AVATAR na posição 1; Adicionar FILME2 ("20 dias em Mariupol", "2023", "Cinema") na posição 1. | FilmNow deve ter adicionado FILME2 com sucesso. Deve exibir a mensagem `FILME ADICIONADO`. |
| 3 | Adicionar um filme já adicionado no sistema em outra posição | Adicionar AVATAR na posição 1; Adicionar AVATAR na posição 3 (vazia). | FilmNow não deve adicionar AVATAR na posição 3. Deve exibir mensagem: `FILME JÁ ADICIONADO`. |
| 4 | Adicionar um novo filme com mesmo nome e ano, mas com local diferente | Adicionar AVATAR na posição 1; Adicionar FILME3 ("Avatar", "2009", "Popcornflix") na posição 3. | FilmNow não deve adicionar AVATAR na posição 3. Deve exibir mensagem: `FILME JÁ ADICIONADO`. |
| 5 | Adicionar um novo filme na posição limite | Adicionar AVATAR na posição 100 (vazia). | FilmNow deve ter adicionado AVATAR com sucesso. Deve exibir a mensagem `FILME ADICIONADO`. |
| 6 | Adicionar um novo filme em uma posição acima do limite | Adicionar AVATAR na posição 101. | FilmNow não deve adicionar AVATAR. Deve exibir a mensagem `POSIÇÃO INVÁLIDA`. |
| 7 | Adicionar um novo filme em uma posição abaixo do limite | Adicionar AVATAR na posição 0. | FilmNow não deve adicionar AVATAR. Deve exibir a mensagem `POSIÇÃO INVÁLIDA`. |
| 8 | Adicionar um novo filme com local vazio | Adicionar FILME2 ("20 dias em Mariupol", "2023", "") na posição 1. | FilmNow não deve adicionar FILME2. Deve exibir a mensagem `FILME INVALIDO`. |
| 9 | Adicionar um novo filme com ano de lançamento vazio | Adicionar FILME2 ("20 dias em Mariupol", "", "Cinema") na posição 1. | FilmNow deve ter adicionado FILME2 com sucesso. Deve exibir a mensagem `FILME ADICIONADO`. |
| 10 | Adicionar um novo filme com nome vazio | Adicionar FILME2 ("", "2023", "Cinema") na posição 1. | FilmNow não deve adicionar FILME2. Deve exibir a mensagem `FILME INVALIDO`. |

> - **TESTE APENAS AQUILO QUE FOI ESPECIFICADO!** Precisa testar se o ano informado é menor ou igual ao ano atual? Não. Se esta regra não foi especificada, não é um comportamento que precisa existir no sistema.
> - **TODO TESTE É INDEPENDENTE!** Sempre comece cada teste do zero. E teste apenas aquilo que é o propósito do teste. Não tente testar 4 funcionalidades diferentes em um único caso de teste pois, em caso de falha, é mais difícil identificar qual é o erro.

### Casos de teste para "Detalhar Filme" (classe FilmNow)

| # | Descrição | Passos | Resultado esperado |
|---|-----------|--------|--------------------|
| 1 | Detalhar Filme adicionado com todos os dados | Adicionar AVATAR na posição 1. | O sistema deve exibir: `Avatar, 2009` / `Disney+` |
| 2 | Detalhar Filme adicionado sem o ano de lançamento | Adicionar FILME2 ("20 dias em Mariupol", "", "Cinema") na posição 1. | O sistema deve exibir: `20 dias em Mariupol` / `Cinema` |
| 3 | Detalhar Filme em uma posição sem filme | Solicitar detalhes de filme na posição 100 (vazia). | O sistema deve retornar nada. |
| 4 | Detalhar Filme em uma posição abaixo do limite inferior | Solicitar detalhes de filme na posição 0. | O sistema deve exibir a mensagem `POSIÇÃO INVÁLIDA`. |
| 5 | Detalhar Filme em uma posição acima do limite superior | Solicitar detalhes de filme na posição 101. | O sistema deve exibir a mensagem `POSIÇÃO INVÁLIDA`. |
| 6 | Detalhar Filme um filme da HotList | Adicionar AVATAR na posição 1; Atribuir Hot ao filme da posição 1; Solicitar detalhes de filme na posição 1. | O sistema deve exibir: `🔥 Avatar, 2009` / `Disney+` |

> ⚠️ Nós desenvolvemos testes que operam nas posições 0, 1, 100 e 101. Essas posições representam **VALORES LIMITE** da especificação. Um valor limite é aquele que está na borda e representa situações extremas da execução do programa.

### Resumo sobre testes

- **Teste todas as unidades (classes) do seu sistema!** Menos as classes de interface com o usuário ou de leitura de arquivos.
- **Teste cada funcionalidade de uma classe, mesmo que ela tenha sido usada (e testada) em outra classe!**
- Os casos de teste da classe `Filme` são com você!

---

## Entrega — via GitHub

Implemente o sistema FilmNow:
- Adicione filmes;
- Exiba detalhes de um filme;
- Mostre toda a sua lista de filmes;
- Adicione, remova e imprima filmes de sua HotList.

Conforme o que está descrito nas seções 1–5 desta especificação. Faça testes de unidade com JUnit, como explicado na seção 6.

É importante que todo código esteja devidamente documentado no formato Javadoc, à exceção das classes de testes. Os arquivos doc não precisam ser enviados para o GitHub.

Você deve entregar um programa com testes para as classes com lógica testável (todas as classes, à exceção das classes de interface com o usuário e para leitura de arquivos que vieram no repositório).

> **IMPORTANTE! NÓS IREMOS AVALIAR SEU CÓDIGO A PARTIR DOS TESTES!**
> Nós não executaremos a sua interface por linha de comando várias vezes, mas pelo contrário, avaliaremos se você fez bons testes, e qual o resultado da execução desses testes!

- Faça bons testes, que explorem as condições limite.
- Faça bons testes, que sejam independentes.
- Faça bons testes, que verifiquem se as condições normais especificadas foram atendidas.

Seu programa será avaliado pela corretude e, principalmente, pelo **DESIGN** do sistema. É importante:
- Usar nomes adequados de variáveis, classes, métodos e parâmetros.
- Fazer um design simples, legível e que funciona. É importante saber, apenas olhando o nome das classes e o nome dos métodos existentes, identificar o que ele faz no código.
