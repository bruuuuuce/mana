package fixture;
import org.springframework.stereotype.Service;
@Service class Entry {
    public void local() { class Helper {} }
    public void anonymous() { new Runnable() { public void run() {} }; }
}
