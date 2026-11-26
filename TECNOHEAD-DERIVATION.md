# Tecnohead Hemma

Esta é uma derivação separada do [Hemma](https://github.com/willsanderson/Hemma)
para avaliação e evolução do painel do Tecnohead Display.

## Base

- Repositório de origem: `willsanderson/Hemma`
- Base inicial: Hemma `2.5.0`
- Integração Home Assistant: domínio `hemma`
- Licença: GPL-3.0, preservada nesta derivação

O repositório original `tecnohead-display` não é alterado por este projeto.
As futuras personalizações do Tecnohead — imagens da casa, seleção de cômodos,
ícones e cartões próprios — serão desenvolvidas aqui, mantendo a possibilidade
de incorporar atualizações do Hemma por meio do remoto `upstream`.

## Fotos do Today

O fluxo de fotos do Tecnohead Display foi incorporado nesta derivação. O
Hemma consulta somente o álbum configurado do Yumi Fotos/Immich, salva as
miniaturas normalizadas em `www/hemma/photos` dentro do Home Assistant e
publica apenas os URLs locais por meio do sensor `Fotos da família`. Fotos em
retrato viram um canvas paisagem 1920×1080 com preenchimento desfocado, sem
esticar nem cortar a imagem original. A chave da API fica somente nas opções
da integração.

## Perfil atual de teste

Na versão `2.5.4`, os cartões automáticos de entidades ficam no modo expandido
na tela inicial e em todas as páginas de cômodos e categorias. Em telas grandes,
o perfil de teste também aumenta a altura, o ícone e a tipografia para tornar a
diferença visível no monitor 1.106. O objetivo é validar a leitura e o uso antes
de decidir o tamanho definitivo para cada tipo de dispositivo.
