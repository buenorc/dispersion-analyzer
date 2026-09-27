# -*- coding: utf-8 -*-
"""
python -m dispersion_analyzer                 -> abre a interface gráfica
python -m dispersion_analyzer projeto.json    -> abre a interface com o projeto
python -m dispersion_analyzer --cli projeto.json [pasta_saida]
                                              -> roda sem interface e grava os resultados
"""
import sys


def main():
    args = sys.argv[1:]
    if args and args[0] == "--cli":
        from .project import Project
        from .analysis import run_analysis
        from .report import save_results, report_text
        prj = Project.load(args[1])
        R = run_analysis(prj, progress=print)
        out = save_results(R, args[2] if len(args) > 2 else prj.resolve(prj.output_dir))
        print(report_text(R))
        print(f"\nResultados gravados em: {out}")
    else:
        from .gui import main as gui
        gui(args)


if __name__ == "__main__":
    main()
