import pytest

import miro_to_excalidraw
from miro_to_excalidraw import read_settings, validate_settings, build_mind_map_nodes_url, API_EXPERIMENTAL

@pytest.fixture
def mock_args():
    return ["script_name", "board_id_123", "/path/to/output.excalidraw"]

class TestReadSettings:
    @staticmethod
    def test_with_args_and_env_var(monkeypatch, mock_args):
        # Mock os.environ to include MIRO_TOKEN
        monkeypatch.setenv("MIRO_TOKEN", "test_token_123")

        board_id, out_path, token = read_settings(mock_args)

        assert board_id == "board_id_123"
        assert out_path == "/path/to/output.excalidraw"
        assert token == "test_token_123"

    @staticmethod
    def test_with_missing_args():
        args = ["script_name"]
        board_id, out_path, token = read_settings(args)

        assert board_id is None
        assert out_path is None
        assert token is None

    @staticmethod
    def test_with_missing_env_var(monkeypatch, mock_args):
        # Mock os.environ without MIRO_TOKEN
        monkeypatch.delenv("MIRO_TOKEN", raising=False)

        board_id, out_path, token = read_settings(mock_args)

        assert board_id == "board_id_123"
        assert out_path == "/path/to/output.excalidraw"
        assert token is None

class TestValidateSettings:
    @staticmethod
    def test_valid_inputs(monkeypatch):
        board_id = "board_id_123"
        out_path = "/path/to/output.excalidraw"
        token = "test_token_123"

        # Replace validate_board_id with a mock function
        monkeypatch.setattr(
            miro_to_excalidraw,
            "validate_board_id",
            lambda *args, **kwargs: True
        )

        result_board_id, result_out_path, result_token = validate_settings(
            board_id, out_path, token
        )

        assert result_board_id == board_id
        assert result_out_path == out_path
        assert result_token == token

    @staticmethod
    def test_missing_board_id():
        with pytest.raises(SystemExit) as sys_exit_result:
            validate_settings(None, "/path/to/output.excalidraw", "test_token_123")
        assert "Errors:" in str(sys_exit_result.value)
        assert "<board_id> argument is missing." in str(sys_exit_result.value)

    @staticmethod
    def test_missing_out_path():
        with pytest.raises(SystemExit) as sys_exit_result:
            validate_settings("board_id_123", None, "test_token_123")
        assert "Errors:" in str(sys_exit_result.value)
        assert "<output.excalidraw> argument is missing." in str(sys_exit_result.value)

    @staticmethod
    def test_missing_token():
        with pytest.raises(SystemExit) as sys_exit_result:
            validate_settings("board_id_123", "/path/to/output.excalidraw", None)
        assert "Errors:" in str(sys_exit_result.value)
        assert "MIRO_TOKEN env var with your Miro access token is missing." in str(sys_exit_result.value)

    @staticmethod
    def test_multiple_errors():
        with pytest.raises(SystemExit) as sys_exit_result:
            validate_settings(None, None, None)
        assert "Errors:" in str(sys_exit_result.value)
        assert "<board_id> argument is missing." in str(sys_exit_result.value)
        assert "<output.excalidraw> argument is missing." in str(sys_exit_result.value)
        assert "MIRO_TOKEN env var with your Miro access token is missing." in str(sys_exit_result.value)

class TestBuildMinMapNodesUrl:
    @staticmethod
    def test_build():
        board_id = "board_id_123"
        expected_url = f"{API_EXPERIMENTAL}/boards/{board_id}/mindmap_nodes"

        result_url = build_mind_map_nodes_url(board_id)

        assert result_url == expected_url

