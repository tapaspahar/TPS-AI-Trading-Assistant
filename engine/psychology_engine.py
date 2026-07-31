class PsychologyEngine:

    def evaluate(self, psychology):

        psychology = psychology.lower()

        if psychology == "calm":
            return 10

        if psychology == "confident":
            return 10

        if psychology == "fear":
            return 4

        if psychology == "greed":
            return 2

        if psychology == "fomo":
            return 1

        if psychology == "revenge":
            return 0

        return 5