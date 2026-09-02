#!/bin/bash
# Exemplo comentado de como construir e rodar a imagem única do SIGMA
# (Dockerfile na raiz). Não é chamado por nenhum processo automático — copie
# os comandos que fizer sentido para o seu terminal, ajustando o caminho do
# --env-file.
#
# Documentação completa: docker/README.md
set -euo pipefail

# 1) Build da imagem (roda a partir da raiz do repositório).
docker build -t sigma .

# 2) Primeira execução: cria o volume nomeado "sigma-dados", que guarda todo
#    o diretório de dados do PostgreSQL (/var/lib/postgresql dentro do
#    container) — sobrevive a `docker rm`/recriação do container.
#    --env-file aponta para um .env preenchido a partir de
#    .env.docker.example (nunca commitado, nunca copiado para dentro da
#    imagem).
docker run -d \
    --name sigma \
    --restart unless-stopped \
    --env-file ./.env.docker \
    -v sigma-dados:/var/lib/postgresql \
    -p 8000:80 \
    sigma

# 3) Acompanhar os três processos supervisionados (postgresql, daphne, nginx):
#    docker logs -f sigma

# 4) Parar e recriar o container reaproveitando o mesmo volume (não perde
#    dado, não recria o cluster PostgreSQL — ver docker/entrypoint.sh):
#    docker stop sigma && docker rm sigma
#    docker run -d --name sigma --restart unless-stopped \
#        --env-file ./.env.docker -v sigma-dados:/var/lib/postgresql \
#        -p 8000:80 sigma
