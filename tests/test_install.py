import pytest

from sr_harness import install as inst
from sr_harness.dospath import bbs_cfg_inbound, dos_path_problems
from sr_harness.session import expand


@pytest.fixture
def drive_c(tmp_path, monkeypatch):
    monkeypatch.setattr(inst, "DRIVE_C", tmp_path)
    return tmp_path


def test_dos_path_is_derived_from_drive_c(drive_c):
    game = drive_c / "bbs" / "doors" / "f900n01"
    game.mkdir(parents=True)
    assert inst.Install(game, "FE.EXE").dos_path == "C:\\BBS\\DOORS\\F900N01"


def test_outside_drive_c_needs_an_explicit_dos_path(drive_c, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    with pytest.raises(ValueError, match="dos_path"):
        inst.Install(elsewhere, "FE.EXE")


def test_a_long_component_is_refused_up_front(drive_c):
    game = drive_c / "doors" / "falconseye"
    game.mkdir(parents=True)
    with pytest.raises(ValueError, match="8.3"):
        inst.Install(game, "FE.EXE")


def test_8_3():
    assert dos_path_problems("C:\\BBS\\DOORS\\B900N01") == []
    assert len(dos_path_problems("C:\\BBS\\DOORS\\B900N01XY\\INBOUND")) == 1
    assert len(dos_path_problems("C:\\BBS\\FILE.TOOL")) == 1


def test_batch_and_command(drive_c):
    game = drive_c / "g"
    game.mkdir()
    i = inst.Install(game, "BRE.EXE")
    i.write_batch("RUN.BAT", "BRE.EXE PLANETARY")
    assert (game / "RUN.BAT").read_bytes() == \
        b"@ECHO OFF\r\nC:\r\nCD C:\\G\r\nBRE.EXE PLANETARY\r\nEXIT\r\n"
    cmd = i.command("RUN.BAT")
    assert cmd[-4:] == ["-K", str(game), "-E", "RUN.BAT"]
    assert i.conf.exists()


def test_full_is_refused_headless(drive_c):
    (drive_c / "g").mkdir()
    with pytest.raises(ValueError, match="interactive"):
        inst.Install(drive_c / "g", "BRE.EXE").run("full", drive_c / "log")


def test_redate_wraps_the_command(drive_c):
    game = drive_c / "g"
    game.mkdir()
    com = drive_c / "REDATE.COM"
    com.write_bytes(b"\xc3")
    i = inst.Install(game, "FE.EXE", redate=com)
    assert i._game_lines("PLANETARY", "20261013") == \
        ["REDATE /i20261013", "FE.EXE PLANETARY", "REDATE /r"]
    assert (game / "REDATE.COM").exists()
    with pytest.raises(ValueError):
        inst.Install(game, "FE.EXE")._game_lines("PLANETARY", "20261013")


def test_doorfile_and_mutex(drive_c):
    game = drive_c / "g"
    game.mkdir()
    i = inst.Install(game, "FE.EXE")
    i.write_doorfile("TEST PILOT 02")
    assert (game / "DOORFILE.SR").read_bytes().split(b"\r\n")[3] == b"0"  # COM 0: local
    (game / "INUSE.FLG").write_text("")
    i.clear_mutex()
    assert not (game / "INUSE.FLG").exists()


def test_bbs_cfg_either_case(tmp_path):
    (tmp_path / "BBS.CFG").write_bytes(b"Sysop\r\nBoard\r\n1:1/1\r\nC:\\G\\INBOUND\r\n")
    assert bbs_cfg_inbound(tmp_path) == "C:\\G\\INBOUND"
    assert inst.find_ci(tmp_path, "bbs.cfg").name == "BBS.CFG"


def test_expand():
    assert expand("Bob<CR><ESC>") == "Bob\r\x1b"


def test_packet_names():
    from sr_harness.mail import parse
    assert parse("900f0102.001") == ("900", "F", 1, 2, 1)
    assert parse("555B0A01.999") == ("555", "B", 10, 1, 999)
    assert parse("fenodes.900") is None
