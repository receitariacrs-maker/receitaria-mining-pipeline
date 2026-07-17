"""
Duas pontas do pipeline que não têm um script "dono" próprio pra avisar sozinhas:
"received" (logo no início, antes até de baixar o vídeo) e "error" (rede de
segurança final, só dispara se nenhuma etapa já tiver avisado o erro específico
dela — ver notifier.py, que cada script usa pra avisar a própria etapa).
"""
import sys

import context
import notifier
import rotulo


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "received"
    ctx = context.load()
    if not ctx.get("chat_id"):
        return  # sem client_payload ainda (ex: falhou antes do bootstrap do contexto)

    if stage == "received":
        # rótulo provisório (link ou legenda/horário) - generate_script.py troca
        # pelo tema+categoria de verdade assim que o roteiro é gerado.
        context.update(rotulo=rotulo.provisorio(ctx))
        notifier.start("📥 Recebi! Vou processar (baixar, transcrever, escrever o roteiro e salvar no Notion).")
    elif stage == "error" and not ctx.get("error_notified"):
        notifier.error(
            "uma etapa inicial (antes de baixar o vídeo)",
            "algo travou logo no começo, sem detalhe específico",
            "Confere se os secrets do repositório estão todos configurados certinho.",
        )


if __name__ == "__main__":
    main()
