# Copyright 2019-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

import cmath
import json
import sys
from collections import Counter, namedtuple

import numpy as np
import pytest
from braket.device_schema.simulators import (
    GateModelSimulatorDeviceCapabilities,
    GateModelSimulatorDeviceParameters,
)
from braket.ir.jaqcd import Program
from braket.task_result import AdditionalMetadata, ResultTypeValue, TaskMetadata

from braket.default_simulator import observables
from braket.default_simulator.result_types import Expectation, Variance
from braket.default_simulator.state_vector_simulator import DefaultSimulator, StateVectorSimulator

CircuitData = namedtuple("CircuitData", "circuit_ir probability_zero")


@pytest.fixture
def grcs_16_qubit():
    with open("test/resources/grcs_16.json") as circuit_file:
        data = json.load(circuit_file)
        return CircuitData(Program.parse_raw(json.dumps(data["ir"])), data["probability_zero"])


@pytest.fixture
def bell_ir():
    return Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ]
            }
        )
    )


@pytest.fixture
def bell_ir_with_result():
    def _bell_ir_with_result(targets=None):
        return Program.parse_raw(
            json.dumps(
                {
                    "instructions": [
                        {"type": "h", "target": 0},
                        {"type": "cnot", "target": 1, "control": 0},
                    ],
                    "results": [
                        {"type": "amplitude", "states": ["11"]},
                        {"type": "expectation", "observable": ["x"], "targets": targets},
                    ],
                }
            )
        )

    return _bell_ir_with_result


@pytest.fixture
def circuit_noise():
    return Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                    {"type": "bit_flip", "target": 0, "probability": 0.15},
                ]
            }
        )
    )


@pytest.mark.parametrize("batch_size", [1, 5, 10])
def test_simulator_run_grcs_16(grcs_16_qubit, batch_size):
    simulator = StateVectorSimulator()
    result = simulator.run(grcs_16_qubit.circuit_ir, qubit_count=16, shots=0, batch_size=batch_size)
    state_vector = result.resultTypes[0].value
    assert cmath.isclose(abs(state_vector[0]) ** 2, grcs_16_qubit.probability_zero, abs_tol=1e-7)


@pytest.mark.parametrize("batch_size", [1, 5, 10])
def test_simulator_run_bell_pair(bell_ir, batch_size):
    simulator = StateVectorSimulator()
    shots_count = 10000
    result = simulator.run(bell_ir, qubit_count=2, shots=shots_count, batch_size=batch_size)

    assert all([len(measurement) == 2] for measurement in result.measurements)
    assert len(result.measurements) == shots_count
    counter = Counter(["".join(measurement) for measurement in result.measurements])
    assert counter.keys() == {"00", "11"}
    assert 0.4 < counter["00"] / (counter["00"] + counter["11"]) < 0.6
    assert 0.4 < counter["11"] / (counter["00"] + counter["11"]) < 0.6
    assert result.taskMetadata == TaskMetadata(
        id=result.taskMetadata.id, deviceId=StateVectorSimulator.DEVICE_ID, shots=shots_count
    )
    assert result.additionalMetadata == AdditionalMetadata(action=bell_ir)


def test_simulator_identity():
    simulator = StateVectorSimulator()
    shots_count = 1000
    result = simulator.run(
        Program.parse_raw(
            json.dumps({"instructions": [{"type": "i", "target": 0}, {"type": "i", "target": 1}]})
        ),
        qubit_count=2,
        shots=shots_count,
    )
    counter = Counter(["".join(measurement) for measurement in result.measurements])
    assert counter.keys() == {"00"}
    assert counter["00"] == shots_count


@pytest.mark.xfail(raises=TypeError)
def test_simulator_instructions_not_supported(circuit_noise):
    simulator = StateVectorSimulator()
    simulator.run(circuit_noise, qubit_count=2, shots=0)


@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_no_results_no_shots(bell_ir):
    simulator = StateVectorSimulator()
    simulator.run(bell_ir, qubit_count=2, shots=0)


@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_amplitude_shots():
    simulator = StateVectorSimulator()
    ir = Program.parse_raw(
        json.dumps(
            {
                "instructions": [{"type": "h", "target": 0}],
                "results": [{"type": "amplitude", "states": ["00"]}],
            }
        )
    )
    simulator.run(ir, qubit_count=2, shots=100)


@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_amplitude_no_shots_invalid_states():
    simulator = StateVectorSimulator()
    ir = Program.parse_raw(
        json.dumps(
            {
                "instructions": [{"type": "h", "target": 0}],
                "results": [{"type": "amplitude", "states": ["0"]}],
            }
        )
    )
    simulator.run(ir, qubit_count=2, shots=0)


@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_statevector_shots():
    simulator = StateVectorSimulator()
    ir = Program.parse_raw(
        json.dumps(
            {"instructions": [{"type": "h", "target": 0}], "results": [{"type": "statevector"}]}
        )
    )
    simulator.run(ir, qubit_count=2, shots=100)


def test_simulator_run_result_types_shots():
    simulator = StateVectorSimulator()
    ir = Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ],
                "results": [{"type": "expectation", "observable": ["z"], "targets": [1]}],
            }
        )
    )
    shots_count = 100
    result = simulator.run(ir, qubit_count=2, shots=shots_count)
    assert all([len(measurement) == 2] for measurement in result.measurements)
    assert len(result.measurements) == shots_count
    assert result.measuredQubits == [0, 1]
    assert not result.resultTypes


def test_simulator_run_result_types_shots_basis_rotation_gates():
    simulator = StateVectorSimulator()
    ir = Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ],
                "basis_rotation_instructions": [{"type": "h", "target": 1}],
                "results": [{"type": "expectation", "observable": ["x"], "targets": [1]}],
            }
        )
    )
    shots_count = 1000
    result = simulator.run(ir, qubit_count=2, shots=shots_count)
    assert all([len(measurement) == 2] for measurement in result.measurements)
    assert len(result.measurements) == shots_count
    assert not result.resultTypes
    assert result.measuredQubits == [0, 1]


@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_result_types_shots_basis_rotation_gates_value_error():
    simulator = StateVectorSimulator()
    ir = Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ],
                "basis_rotation_instructions": [{"type": "foo", "target": 1}],
                "results": [{"type": "expectation", "observable": ["x"], "targets": [1]}],
            }
        )
    )
    shots_count = 1000
    simulator.run(ir, qubit_count=2, shots=shots_count)


@pytest.mark.parametrize(
    "ir, qubit_count",
    [
        (
            Program.parse_raw(
                json.dumps(
                    {
                        "instructions": [{"type": "z", "target": 2}],
                        "basis_rotation_instructions": [],
                        "results": [],
                    }
                )
            ),
            1,
        ),
        (
            Program.parse_raw(
                json.dumps(
                    {
                        "instructions": [{"type": "h", "target": 0}],
                        "basis_rotation_instructions": [{"type": "z", "target": 3}],
                        "results": [],
                    }
                )
            ),
            2,
        ),
    ],
)
@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_non_contiguous_qubits(ir, qubit_count):
    simulator = StateVectorSimulator()
    shots_count = 1000
    simulator.run(ir, qubit_count=qubit_count, shots=shots_count)


@pytest.mark.parametrize(
    "ir, qubit_count",
    [
        (
            Program.parse_raw(
                json.dumps(
                    {
                        "results": [{"targets": [2], "type": "expectation", "observable": ["z"]}],
                        "basis_rotation_instructions": [],
                        "instructions": [{"type": "z", "target": 0}],
                    }
                )
            ),
            1,
        ),
        (
            Program.parse_raw(
                json.dumps(
                    {
                        "results": [{"targets": [2], "type": "expectation", "observable": ["z"]}],
                        "basis_rotation_instructions": [],
                        "instructions": [{"type": "z", "target": 0}, {"type": "z", "target": 1}],
                    }
                )
            ),
            2,
        ),
    ],
)
@pytest.mark.xfail(raises=ValueError)
def test_simulator_run_observable_references_invalid_qubit(ir, qubit_count):
    simulator = StateVectorSimulator()
    shots_count = 0
    simulator.run(ir, qubit_count=qubit_count, shots=shots_count)


@pytest.mark.parametrize("batch_size", [1, 5, 10])
@pytest.mark.parametrize("targets", [(None), ([1]), ([0])])
def test_simulator_bell_pair_result_types(bell_ir_with_result, targets, batch_size):
    simulator = StateVectorSimulator()
    ir = bell_ir_with_result(targets)
    result = simulator.run(ir, qubit_count=2, shots=0, batch_size=batch_size)
    assert len(result.resultTypes) == 2
    assert result.resultTypes[0] == ResultTypeValue.construct(
        type=ir.results[0], value={"11": complex(1 / 2 ** 0.5)}
    )
    assert result.resultTypes[1] == ResultTypeValue.construct(
        type=ir.results[1], value=(0 if targets else [0, 0])
    )
    assert result.taskMetadata == TaskMetadata(
        id=result.taskMetadata.id, deviceId=StateVectorSimulator.DEVICE_ID, shots=0
    )
    assert result.additionalMetadata == AdditionalMetadata(action=ir)


@pytest.mark.xfail(raises=ValueError)
def test_simulator_fails_samples_0_shots():
    simulator = StateVectorSimulator()
    prog = Program.parse_raw(
        json.dumps(
            {
                "instructions": [{"type": "h", "target": 0}],
                "results": [{"type": "sample", "observable": ["x"], "targets": [0]}],
            }
        )
    )
    simulator.run(prog, qubit_count=1, shots=0)


@pytest.mark.parametrize(
    "result_types,expected_expectation,expected_variance",
    [
        (
            [
                {"type": "expectation", "observable": ["x"], "targets": [1]},
                {"type": "variance", "observable": ["x"], "targets": [1]},
            ],
            0,
            1,
        ),
        (
            [
                {"type": "expectation", "observable": ["x"]},
                {"type": "variance", "observable": ["x"], "targets": [1]},
            ],
            [0, 0],
            1,
        ),
        (
            [
                {
                    "type": "expectation",
                    "observable": [[[[0, 0], [1, 0]], [[1, 0], [0, 0]]]],
                    "targets": [1],
                },
                {
                    "type": "variance",
                    "observable": [[[[0, 0], [1, 0]], [[1, 0], [0, 0]]]],
                    "targets": [1],
                },
            ],
            0,
            1,
        ),
        (
            [
                {
                    "type": "expectation",
                    "observable": ["x", [[[0, 0], [1, 0]], [[1, 0], [0, 0]]]],
                    "targets": [0, 1],
                },
                {
                    "type": "expectation",
                    "observable": ["x", [[[0, 0], [1, 0]], [[1, 0], [0, 0]]]],
                    "targets": [0, 1],
                },
            ],
            1,
            1,
        ),
    ],
)
def test_simulator_accepts_overlapping_targets_same_observable(
    result_types, expected_expectation, expected_variance
):
    simulator = StateVectorSimulator()
    prog = Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ],
                "results": result_types,
            }
        )
    )
    result = simulator.run(prog, qubit_count=2, shots=0)
    expectation = result.resultTypes[0].value
    variance = result.resultTypes[1].value
    assert np.allclose(expectation, expected_expectation)
    assert np.allclose(variance, expected_variance)


@pytest.mark.xfail(raises=ValueError)
@pytest.mark.parametrize(
    "result_types",
    [
        (
            [
                {"type": "expectation", "observable": ["y"]},
                {"type": "variance", "observable": ["x"], "targets": [1]},
            ]
        ),
        (
            [
                {"type": "expectation", "observable": ["y"], "targets": [1]},
                {"type": "variance", "observable": ["x"], "targets": [1]},
            ]
        ),
        (
            [
                {
                    "type": "expectation",
                    "observable": [[[[0, 0], [1, 0]], [[1, 0], [0, 0]]]],
                    "targets": [1],
                },
                {
                    "type": "variance",
                    "observable": [[[[1, 0], [0, 0]], [[0, 0], [1, 0]]]],
                    "targets": [1],
                },
            ]
        ),
        (
            [
                {
                    "type": "expectation",
                    "observable": ["x", [[[0, 0], [1, 0]], [[1, 0], [0, 0]]]],
                    "targets": [0, 1],
                },
                {"type": "variance", "observable": ["y", "x"], "targets": [0, 1]},
            ]
        ),
        (
            [
                {"type": "expectation", "observable": ["i"]},
                {"type": "variance", "observable": ["y"]},
            ]
        ),
    ],
)
def test_simulator_fails_overlapping_targets_different_observable(result_types):
    simulator = StateVectorSimulator()
    prog = Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ],
                "results": result_types,
            }
        )
    )
    simulator.run(prog, qubit_count=2, shots=0)


@pytest.mark.xfail(raises=ValueError)
def test_simulator_fails_same_observable_different_target_order():
    simulator = StateVectorSimulator()
    prog = Program.parse_raw(
        json.dumps(
            {
                "instructions": [
                    {"type": "h", "target": 0},
                    {"type": "cnot", "target": 1, "control": 0},
                ],
                "results": [
                    {
                        "type": "expectation",
                        "observable": [
                            [
                                [[0, 0], [1, 0], [0, 0], [0, 0]],
                                [[1, 0], [0, 0], [0, 0], [0, 0]],
                                [[0, 0], [0, 0], [0, 0], [-1, 0]],
                                [[0, 0], [0, 0], [-1, 0], [0, 0]],
                            ]
                        ],
                        "targets": [0, 1],
                    },
                    {
                        "type": "variance",
                        "observable": [
                            [
                                [[0, 0], [1, 0], [0, 0], [0, 0]],
                                [[1, 0], [0, 0], [0, 0], [0, 0]],
                                [[0, 0], [0, 0], [0, 0], [-1, 0]],
                                [[0, 0], [0, 0], [-1, 0], [0, 0]],
                            ]
                        ],
                        "targets": [1, 0],
                    },
                ],
            }
        )
    )
    simulator.run(prog, qubit_count=2, shots=0)


@pytest.mark.parametrize(
    "obs1,obs2",
    [
        (observables.PauliX([1]), observables.PauliX(None)),
        (observables.PauliZ([1]), observables.PauliZ(None)),
        (observables.Hermitian(np.eye(2), [1]), observables.Hermitian(np.eye(2), None)),
    ],
)
def test_validate_and_consolidate_observable_result_types_none(obs1, obs2):
    obs_rts = [
        Expectation(obs1),
        Variance(obs2),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 2)
    assert len(actual_obs) == 1
    assert actual_obs[0].measured_qubits is None


@pytest.mark.parametrize(
    "obs",
    [(observables.PauliX([1])), (observables.PauliZ([1])), (observables.Hermitian(np.eye(2), [1]))],
)
def test_validate_and_consolidate_observable_result_types_same_target(obs):
    obs_rts = [
        Expectation(obs),
        Variance(obs),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 2)
    assert len(actual_obs) == 1
    assert actual_obs[0].measured_qubits == (1,)


def test_validate_and_consolidate_observable_result_types_tensor_product():
    obs_rts = [
        Expectation(observables.TensorProduct([observables.PauliX([0]), observables.PauliY([1])])),
        Variance(observables.TensorProduct([observables.PauliX([0]), observables.PauliY([1])])),
        Expectation(observables.TensorProduct([observables.PauliX([2]), observables.PauliY([3])])),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 4)
    assert len(actual_obs) == 4
    assert [obs.measured_qubits for obs in actual_obs] == [(0,), (1,), (2,), (3,)]


def test_validate_and_consolidate_observable_result_types_tensor_product_shared_factor():
    obs_rts = [
        Expectation(observables.PauliX([0])),
        Variance(observables.TensorProduct([observables.PauliX([0]), observables.PauliY([1])])),
        Expectation(observables.TensorProduct([observables.PauliY([1]), observables.PauliX([2])])),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 3)
    assert len(actual_obs) == 3
    assert [obs.measured_qubits for obs in actual_obs] == [(0,), (1,), (2,)]


def test_validate_and_consolidate_observable_result_types_tensor_product_hermitian_shared_factor():
    obs_rts = [
        Expectation(observables.PauliX([0])),
        Variance(
            observables.TensorProduct(
                [
                    observables.PauliX([0]),
                    observables.Hermitian(np.eye(4), [1, 2]),
                    observables.PauliY([3]),
                ]
            )
        ),
        Expectation(
            observables.TensorProduct(
                [observables.Hermitian(np.eye(4), [1, 2]), observables.PauliY([3])]
            )
        ),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 4)
    assert len(actual_obs) == 3
    assert [obs.measured_qubits for obs in actual_obs] == [
        (0,),
        (
            1,
            2,
        ),
        (3,),
    ]


def test_validate_and_consolidate_observable_result_types_identity_allowed():
    obs_rts = [
        Expectation(observables.PauliX([0])),
        Expectation(observables.Identity([4])),
        Variance(observables.Identity([2])),
        Variance(observables.TensorProduct([observables.Identity([1]), observables.PauliX([3])])),
        Expectation(
            observables.TensorProduct([observables.PauliY([1]), observables.Identity([3])])
        ),
        Variance(observables.Identity([0])),
        Expectation(observables.PauliX([2])),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 5)
    assert len(actual_obs) == 5
    assert [obs.measured_qubits for obs in actual_obs] == [(0,), (3,), (1,), (2,), (4,)]


def test_observable_hash_tensor_product():
    matrix = np.eye(4)
    obs = observables.TensorProduct(
        [observables.PauliX([0]), observables.Hermitian(matrix, [1, 2]), observables.PauliY([1])]
    )
    hash_dict = StateVectorSimulator._observable_hash(obs)
    matrix_hash = hash_dict[1]
    assert hash_dict == {0: "PauliX", 1: matrix_hash, 2: matrix_hash, 3: "PauliY"}


@pytest.mark.parametrize(
    "obs1,obs2",
    [
        (observables.PauliX([1]), observables.PauliX([2])),
        (observables.PauliZ([1]), observables.PauliZ([2])),
        (observables.Hermitian(np.eye(2), [1]), observables.Hermitian(np.eye(2), [2])),
    ],
)
def test_validate_and_consolidate_observable_result_types_targets(obs1, obs2):
    obs_rts = [
        Expectation(obs1),
        Expectation(obs2),
    ]
    actual_obs = StateVectorSimulator._validate_and_consolidate_observable_result_types(obs_rts, 3)
    assert len(actual_obs) == 2
    assert actual_obs[0].measured_qubits == (1,)
    assert actual_obs[1].measured_qubits == (2,)


def test_properties():
    simulator = StateVectorSimulator()
    observables = ["X", "Y", "Z", "H", "I", "Hermitian"]
    max_shots = sys.maxsize
    qubit_count = 26
    expected_properties = GateModelSimulatorDeviceCapabilities.parse_obj(
        {
            "service": {
                "executionWindows": [
                    {
                        "executionDay": "Everyday",
                        "windowStartHour": "00:00",
                        "windowEndHour": "23:59:59",
                    }
                ],
                "shotsRange": [0, max_shots],
            },
            "action": {
                "braket.ir.jaqcd.program": {
                    "actionType": "braket.ir.jaqcd.program",
                    "version": ["1"],
                    "supportedOperations": [
                        "CCNot",
                        "CNot",
                        "CPhaseShift",
                        "CPhaseShift00",
                        "CPhaseShift01",
                        "CPhaseShift10",
                        "CSwap",
                        "CY",
                        "CZ",
                        "H",
                        "I",
                        "ISwap",
                        "PSwap",
                        "PhaseShift",
                        "Rx",
                        "Ry",
                        "Rz",
                        "S",
                        "Si",
                        "Swap",
                        "T",
                        "Ti",
                        "Unitary",
                        "V",
                        "Vi",
                        "X",
                        "XX",
                        "XY",
                        "Y",
                        "YY",
                        "Z",
                        "ZZ",
                    ],
                    "supportedResultTypes": [
                        {
                            "name": "Sample",
                            "observables": observables,
                            "minShots": 1,
                            "maxShots": max_shots,
                        },
                        {
                            "name": "Expectation",
                            "observables": observables,
                            "minShots": 0,
                            "maxShots": max_shots,
                        },
                        {
                            "name": "Variance",
                            "observables": observables,
                            "minShots": 0,
                            "maxShots": max_shots,
                        },
                        {"name": "Probability", "minShots": 0, "maxShots": max_shots},
                        {"name": "StateVector", "minShots": 0, "maxShots": 0},
                        {"name": "DensityMatrix", "minShots": 0, "maxShots": 0},
                        {"name": "Amplitude", "minShots": 0, "maxShots": 0},
                    ],
                }
            },
            "paradigm": {"qubitCount": qubit_count},
            "deviceParameters": GateModelSimulatorDeviceParameters.schema(),
        }
    )
    assert simulator.properties == expected_properties


def test_alias():
    assert StateVectorSimulator().properties == DefaultSimulator().properties
