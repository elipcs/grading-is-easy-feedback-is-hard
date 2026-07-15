# Referência da estrutura inicial fornecida no lab

O Lab 03 não parte do zero. Havia uma estrutura inicial fornecida pela disciplina. Use como referência operacional o repositório `starter-reference`, que aqui representa o estado muito próximo do template base.

## Regra central de avaliação

Não atribua crédito positivo pela simples presença da estrutura inicial, de classes já criadas, do menu textual, do leitor de CSV, de Javadocs herdados ou de um array simples de filmes se isso não foi efetivamente evoluído pelo estudante.

Avalie apenas o que o estudante implementou ou modificou em cima dessa base para cumprir o enunciado.

## Implicações práticas

- A mera existência de `MainFilmNow.java` não vale ponto.
- A mera existência de `LeitorFilmNow.java` não vale ponto.
- A mera existência de `FilmNow.java` com array simples de `String` não vale ponto.
- A navegação básica de menu e a carga inicial de CSV não devem ser tratadas como evidências de aprendizado suficiente no critério funcional.
- Não elogie "boa organização inicial" se ela coincide apenas com o starter code.
- Só reconheça como acerto aquilo que ultrapassa claramente a estrutura base.

## Sinais de starter code que não devem receber crédito por si só

- classe `FilmNow` armazenando apenas `String[] filmes`
- método `cadastraFilme(int posicao, String nome, int ano, String local)` que só faz `this.filmes[posicao] = nome`
- classe `MainFilmNow` com menu `(A)`, `(M)`, `(D)`, `(S)`
- leitura inicial de `filmes_inicial.csv`
- classe `LeitorFilmNow` que apenas percorre CSV e chama `cadastraFilme`

## Estrutura base de referência

```text
src/filmnow/FilmNow.java
src/filmnow/MainFilmNow.java
src/filmnow/LeitorFilmNow.java
```

## Excertos representativos da base

### FilmNow.java

```java
public class FilmNow {
    private static final int TAMANHO = 100;
    private String[] filmes;

    public FilmNow() {
        this.filmes = new String[TAMANHO];
    }

    public String[] getFilmes() {
        return this.filmes.clone();
    }

    public String getFilme(int posicao) {
        return filmes[posicao];
    }

    public void cadastraFilme(int posicao, String nome, int ano, String local) {
        this.filmes[posicao] = nome;
    }
}
```

### MainFilmNow.java

```java
while (true) {
    escolha = menu(scanner);
    comando(escolha, fn, scanner);
}
```

```java
private static void adicionaFilme(FilmNow fn, Scanner scanner) {
    System.out.print("\\nPosicao no sistema> ");
    int posicao = scanner.nextInt();
    System.out.print("\\nNome> ");
    String nome = scanner.next();
    System.out.print("\\nAno> ");
    String ano = scanner.next();
    System.out.print("\\nLocal> ");
    String local = scanner.next();
    fn.cadastraFilme(posicao, nome, Integer.parseInt(ano), local);
}
```

### LeitorFilmNow.java

```java
private void processaLinhaCsvFilmes(String[] campos, FilmNow fn) {
    int posicao = Integer.parseInt(campos[COLUNA_POSICAO]);
    String nome = campos[COLUNA_NOME].trim();
    String ano = campos[COLUNA_ANO].trim();
    String local = campos[COLUNA_LOCAL].trim();

    fn.cadastraFilme(posicao, nome, Integer.parseInt(ano), local);
}
```

## Regra de julgamento para casos próximos da base

Se a submissão permanece muito próxima da estrutura inicial e não demonstra implementação substantiva dos requisitos do enunciado, a avaliação deve refletir isso com notas muito baixas. Nesses casos, não descreva o starter como mérito do estudante.

## Regra de severidade para casos idênticos ao starter

Se o pacote da submissão indicar `similarity_label = identica_ao_starter`, interprete isso como ausência de implementação relevante do estudante.

Nesses casos:

- atribua `0` em `funcionalidade_basica`
- atribua `0` em `testes`
- atribua `0` em `criacao_de_classes`
- atribua `0` em `uso_de_referencias`
- atribua `0` em `uso_de_array_colecoes`
- atribua `0` em `divisao_de_funcionalidades`
- atribua `0` em `legibilidade_e_documentacao`
- a `nota total` deve ser exatamente `0`

Não conceda nenhum crédito por menu, leitura de CSV, Javadocs herdados, array base, separação inicial de arquivos ou qualquer outro elemento que faça parte do starter code.

## Regra para casos muito próximos ao starter

Se o pacote indicar `similarity_label = muito_proxima_do_starter`, trate a submissão como implementação extremamente insuficiente.

Nesses casos:

- as notas devem permanecer muito próximas de `0`
- só atribua algum ponto se houver evidência concreta de implementação adicional real
- a `nota total` só deve ultrapassar `0` se houver modificação substantiva claramente observável
