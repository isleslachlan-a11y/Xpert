"""
Meridian — Natural ventilation calculator.
Standard: AS 1668.4—2012, Simple Procedure (Cl. 3.4).

Three arrangements:
  - Direct (Cl. 3.2.1): room opens directly to outside
  - Borrowed (Cl. 3.2.2): room borrows ventilation through an adjoining space
  - Flowthrough (Cl. 3.2.3): cross-ventilation through the room

Safety factors by building class (Cl. 3.4.x):
  Class 1, 2, 4  → 5%
  Class 5–9      → 10%
  Classrooms <16 → 12.5%

Port methodology from AS1668_4_Ventilation_Calculator.html exactly.
"""

# TODO: Implement calculate_natural_ventilation(room_area, building_class, arrangement, **kwargs) -> dict
#   Return dict must include:
#     - required_external_area (m²)
#     - required_internal_area (m², for borrowed/flowthrough only)
#     - safety_factor (fraction)
#     - arrangement (str)
#     - clause_ref (str)  — e.g. "AS 1668.4—2012 Cl. 3.4.1"
#     - method (str)      — human-readable description of the method used
#
# TODO: Implement format_natural_ventilation_result(result: dict) -> str
#   Returns agent-readable formatted string of the result.


def calculate_natural_ventilation(
    room_area: float,
    building_class: str,
    arrangement: str,
) -> dict:
    # TODO: implement — port from AS1668_4_Ventilation_Calculator.html
    raise NotImplementedError


def format_natural_ventilation_result(result: dict) -> str:
    # TODO: implement
    raise NotImplementedError


if __name__ == "__main__":
    # TODO: add worked example matching AS 1668.4—2012 Appendix example
    pass
