# runs everything in order
import correction
import figures
import radiation_screening
import validation

if __name__ == "__main__":
    for name, step in [("Validation statistics", validation),
                       ("Radiation screening", radiation_screening),
                       ("Correction models", correction),
                       ("Figures", figures)]:
        print(f"\n===== {name} =====")
        step.main()
