from enum import IntEnum

class PuryfiObjectLabel(IntEnum):
    Tummy = 0
    TummyCovered = 1
    Buttocks = 2
    ButtocksCovered = 3
    FemaleBreast = 4
    FemaleBreastCovered = 5
    FemaleGenitals = 6
    FemaleGenitalsCovered = 7
    MaleGenitalsCovered = 8
    MaleGenitals = 9
    MaleBreast = 10
    MaleBreastCovered = 11
    FemaleFace = 12
    MaleFace = 13
    FootCovered = 14
    Foot = 15
    ArmpitCovered = 16
    Armpit = 17
    AnusCovered = 18
    Anus = 19
    Eye = 20
    Mouth = 21
    NippleCovered = 22
    Nipple = 23
    HandCovered = 24
    Hand = 25

    @classmethod
    def get_name(cls, value: int) -> str | None:
        try:
            return cls(value).name
        except ValueError:
            return None