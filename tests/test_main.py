from chatbot.main import main

def test_main(capsys):
    main()
    captured = capsys.readouterr()
    assert "Hello from my_package!" in captured.out
